#!/usr/bin/env python3
# Setup: export NTFY_TOPIC=your-private-topic in ~/.zshrc
# Generate server token: python3 -c "import secrets; print(secrets.token_hex(24))" > ~/.claude/hooks/.server_token
import json, sys, os, subprocess, urllib.request, time, socket, secrets

LOG     = os.path.expanduser("~/.claude/hooks/notify.log")
PENDING = os.path.expanduser("~/.claude/hooks/.pending_notify.json")

def log(msg):
    with open(LOG, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

try:
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
except Exception as e:
    log(f"ERROR reading stdin: {e}")
    data = {}

event = sys.argv[1] if len(sys.argv) > 1 else "unknown"

# ── user_prompt: cancel any pending notification ──────────────────────────────
if event == "user_prompt":
    try:
        os.remove(PENDING)
        log("user_prompt: cancelled pending notification")
    except FileNotFoundError:
        pass
    sys.exit(0)

# ── delayed: fires 5s after schedule, sends if still pending ─────────────────
if event == "delayed":
    unique_id = sys.argv[2] if len(sys.argv) > 2 else ""
    time.sleep(5)
    try:
        with open(PENDING) as f:
            pending = json.load(f)
        if pending.get("id") != unique_id:
            log("delayed: newer event queued, skipping")
            sys.exit(0)
        title       = pending["title"]
        body        = pending["body"]
        ntfy_headers = pending.get("ntfy_headers", {})
        os.remove(PENDING)
        log(f"delayed: user was away, sending notification")
    except (FileNotFoundError, json.JSONDecodeError):
        log("delayed: cancelled (user was present)")
        sys.exit(0)

    # macOS popup
    mac_body = body.split("\n")[0][:200]
    mac_env = os.environ.copy()
    mac_env["_NOTIFY_TITLE"] = title
    mac_env["_NOTIFY_BODY"]  = mac_body
    result = subprocess.run(
        ["osascript", "-e",
         'display notification (system attribute "_NOTIFY_BODY") with title (system attribute "_NOTIFY_TITLE")'],
        env=mac_env, capture_output=True
    )
    if result.returncode == 0:
        log("mac notif fired")
    else:
        log(f"mac notif error: {result.stderr.decode().strip()}")

    for _ in range(3):
        subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"])
        time.sleep(0.3)

    # Phone push
    topic = os.environ.get("NTFY_TOPIC", "cc-2b5a6c24de06d58f9b459d30")
    if topic and ntfy_headers:
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}",
            data=body.encode()[:4096],
            headers=ntfy_headers,
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            log("phone notif fired")
        except Exception as e:
            log(f"phone notif error: {e}")

    sys.exit(0)

# ── Log incoming event ────────────────────────────────────────────────────────
stop_hook_active = data.get("stop_hook_active", "n/a")
log(f"event={event} stop_hook_active={stop_hook_active}")
for key in ("last_assistant_message", "message"):
    if key in data:
        log(f"  {key}={str(data[key])[:120]}")

topic = os.environ.get("NTFY_TOPIC", "cc-2b5a6c24de06d58f9b459d30")

# ── Helpers ───────────────────────────────────────────────────────────────────

def ascii_header(s):
    return s.encode("ascii", errors="replace").decode("ascii")

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
                    inp  = block.get("input", {})
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

# ── Build title + body ────────────────────────────────────────────────────────

if event == "stop":
    title = "Claude is done - your turn"
    last_msg = data.get("last_assistant_message", "").strip()
    transcript_path = data.get("transcript_path", "")
    _, edited_files, bash_cmds = parse_last_turn(transcript_path)
    parts = []
    if last_msg:
        parts.append(last_msg[:600] + ("..." if len(last_msg) > 600 else ""))
    meta = []
    if edited_files:
        meta.append("Edited: " + ", ".join(edited_files[:6]))
    if bash_cmds:
        meta.append("Ran: " + " | ".join(bash_cmds[:4]))
    if meta:
        parts.append("\n" + "\n".join(meta))
    body = "\n".join(parts) if parts else "Claude finished its response."

elif event == "permission_prompt":
    title = "Permission needed - Claude is waiting"
    tool = data.get("tool_name", "unknown tool")
    inp  = data.get("input", {})
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
    title = "Claude is idle - waiting for you"
    idle_msg = data.get("message", "").strip()
    transcript_path = data.get("transcript_path", find_recent_transcript())
    _, edited_files, bash_cmds = parse_last_turn(transcript_path)
    parts = []
    if idle_msg:
        parts.append(idle_msg[:600] + ("..." if len(idle_msg) > 600 else ""))
    meta = []
    if edited_files:
        meta.append("Last edited: " + ", ".join(edited_files[:6]))
    if bash_cmds:
        meta.append("Last ran: " + " | ".join(bash_cmds[:4]))
    if meta:
        parts.append("\n" + "\n".join(meta))
    body = "\n".join(parts) if parts else "Claude has been waiting for your input for a while."

else:
    title = "Claude needs your attention"
    body  = json.dumps(data, indent=2)[:600] if isinstance(data, dict) else str(data)[:400]

# ── Build ntfy headers (computed now, stored in pending file) ─────────────────

PRIORITY = {"stop": "high", "permission_prompt": "urgent", "elicitation": "high", "idle": "high"}

ntfy_headers = {"Title": ascii_header(title), "Priority": PRIORITY.get(event, "high")}

local_ip = get_local_ip()
token    = get_server_token()

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

# ── Schedule delayed notification (fires in 5s if user doesn't type) ─────────

unique_id = secrets.token_hex(8)
with open(PENDING, "w") as f:
    json.dump({"id": unique_id, "title": title, "body": body, "ntfy_headers": ntfy_headers}, f)

subprocess.Popen(
    [sys.executable, os.path.abspath(__file__), "delayed", unique_id],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    start_new_session=True
)
log(f"event={event}: notification scheduled (fires in 5s if idle)")
