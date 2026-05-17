#!/usr/bin/env python3
# Setup: export NTFY_TOPIC=your-private-topic in ~/.zshrc
# Generate server token: python3 -c "import secrets; print(secrets.token_hex(24))" > ~/.claude/hooks/.server_token
import json, sys, os, subprocess, urllib.request, time, socket

data = json.load(sys.stdin)
event = sys.argv[1] if len(sys.argv) > 1 else "unknown"
topic = os.environ.get("NTFY_TOPIC", "")

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None

def get_server_token():
    try:
        with open(os.path.expanduser("~/.claude/hooks/.server_token")) as f:
            return f.read().strip()
    except Exception:
        return None

def find_recent_transcript():
    """Find the most recently modified session transcript across all projects."""
    projects_dir = os.path.expanduser("~/.claude/projects")
    try:
        best = ("", 0)
        for root, _, filenames in os.walk(projects_dir):
            for fn in filenames:
                if fn.endswith(".jsonl"):
                    fp = os.path.join(root, fn)
                    mtime = os.path.getmtime(fp)
                    if mtime > best[1]:
                        best = (fp, mtime)
        return best[0]
    except Exception:
        return None

def parse_last_turn(transcript_path):
    """Returns (response_text, edited_files, bash_commands) from the last assistant turn."""
    text, edited, cmds = "", [], []
    if not transcript_path or not os.path.exists(transcript_path):
        return text, edited, cmds
    try:
        with open(transcript_path) as f:
            lines = [l for l in f.read().strip().splitlines() if l]
        for line in reversed(lines):
            entry = json.loads(line)
            if entry.get("role") != "assistant":
                continue
            content = entry.get("content", "")
            if not isinstance(content, list):
                text = str(content).strip()
                break
            for block in content:
                btype = block.get("type", "")
                if btype == "text":
                    text = text or block.get("text", "").strip()
                elif btype == "tool_use":
                    name = block.get("name", "")
                    inp = block.get("input", {})
                    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                        fp = inp.get("file_path", "")
                        if fp and os.path.basename(fp) not in edited:
                            edited.append(os.path.basename(fp))
                    elif name == "Bash":
                        cmd = inp.get("command", "").strip()
                        if cmd:
                            cmds.append(cmd[:80])
            break
    except Exception:
        pass
    return text, edited, cmds

def build_turn_summary(transcript_path):
    """Build a rich body string from a transcript, used by stop and idle."""
    response_text, edited_files, bash_cmds = parse_last_turn(transcript_path)
    parts = []
    if response_text:
        parts.append(response_text[:600] + ("…" if len(response_text) > 600 else ""))
    meta = []
    if edited_files:
        meta.append("Edited: " + ", ".join(edited_files[:6]))
    if bash_cmds:
        meta.append("Ran: " + " | ".join(bash_cmds[:4]))
    if meta:
        parts.append("\n" + "\n".join(meta))
    return "\n".join(parts) if parts else None


# ── Priority map (urgent bypasses DND on phone) ───────────────────────────────
PRIORITY = {
    "stop":              "high",
    "permission_prompt": "urgent",
    "elicitation":       "high",
    "idle":              "high",
}

# ── Build contextual title + body ─────────────────────────────────────────────

if event == "stop":
    title = "Claude is done — your turn"
    transcript_path = data.get("transcript_path", "")
    body = build_turn_summary(transcript_path) or "Claude finished its response."

elif event == "permission_prompt":
    title = "Permission needed — Claude is waiting"
    tool = data.get("tool_name", "unknown tool")
    inp = data.get("input", {})
    if "command" in inp:
        body = f"{tool} wants to run:\n\n{inp['command'][:800]}"
    elif "file_path" in inp:
        body = f"{tool} wants to edit:\n{inp['file_path']}"
    else:
        body = f"{tool}\n{json.dumps(inp, indent=2)[:600]}"

elif event == "elicitation":
    title = "Claude has a question"
    msg = data.get("message", data.get("prompt", data.get("content", "")))
    if isinstance(msg, list):
        msg = " ".join(c.get("text", "") for c in msg if c.get("type") == "text")
    body = str(msg)[:1200] if msg else "Claude is waiting for your answer"

elif event == "idle":
    title = "Claude is idle — waiting for you"
    transcript_path = data.get("transcript_path", find_recent_transcript())
    summary = build_turn_summary(transcript_path)
    if summary:
        body = "Still waiting on your reply. Last thing:\n\n" + summary[:600]
    else:
        body = "Claude has been waiting for your input for a while."

else:
    title = "Claude needs your attention"
    body = json.dumps(data, indent=2)[:600] if isinstance(data, dict) else str(data)[:400]


# ── macOS popup + 3x chime ────────────────────────────────────────────────────

mac_body = body.split("\n")[0][:200]
safe_body = mac_body.replace('"', '\\"').replace("'", "\\'")
safe_title = title.replace('"', '\\"').replace("'", "\\'")
subprocess.run(["osascript", "-e", f'display notification "{safe_body}" with title "{safe_title}"'], capture_output=True)

for _ in range(3):
    subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"])
    time.sleep(0.3)


# ── Phone push via ntfy ───────────────────────────────────────────────────────

if topic:
    priority = PRIORITY.get(event, "high")
    ntfy_headers = {"Title": title, "Priority": priority}

    local_ip = get_local_ip()
    token = get_server_token()

    if event == "permission_prompt" and local_ip and token:
        base = f"http://{local_ip}:9191"
        auth = f"headers.Authorization=Bearer {token}"
        ntfy_headers["Actions"] = (
            f"http, Approve, {base}/approve, method=POST, {auth}; "
            f"http, Deny, {base}/deny, method=POST, {auth}"
        )
    elif event in ("elicitation", "idle", "stop") and local_ip and token:
        ntfy_headers["Actions"] = (
            f"http, Focus Mac, http://{local_ip}:9191/focus, "
            f"method=POST, headers.Authorization=Bearer {token}"
        )

    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=body.encode()[:4096],
        headers=ntfy_headers,
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass
