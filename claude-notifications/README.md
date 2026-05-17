# claude-notifications

Get notified on your phone and Mac whenever Claude Code needs your attention — with full context about what it did or what it's waiting for.

## What you get

| Event | Notification | Action buttons |
|---|---|---|
| Claude finishes a response | What it said + files edited + commands run | Focus Mac |
| Permission needed | Tool + exact command waiting for approval | **Approve** / **Deny** |
| Claude asks a question | The full question text | Focus Mac |
| Claude is idle | What it was last working on | Focus Mac |

**Approve/Deny** sends the keypress directly to your terminal — no need to walk over to your Mac.  
**Focus Mac** brings your Terminal/iTerm window to the front when you do walk over.

> Action buttons work on your home WiFi. Phone notifications work anywhere.

## Prerequisites

- macOS (uses AppleScript + LaunchAgents)
- Python 3 (pre-installed on macOS)
- [ntfy](https://ntfy.sh) app on your phone (free, no account needed)
- [Claude Code](https://claude.ai/code)

## Setup

```bash
git clone <this-repo> claude-notifications
cd claude-notifications
bash setup.sh
```

Then follow the 2 steps it prints:
1. Add `export NTFY_TOPIC=your-topic` to `~/.zshrc`
2. Subscribe to that topic in the ntfy app

Open a new Claude Code session and you're live.

## How it works

- **`notify.py`** — a Claude Code hook script triggered on `Stop`, `Notification` (permission, question, idle) events. Sends a macOS popup + 3 chimes + ntfy push with full context.
- **`focus_server.py`** — a tiny HTTP server (port 9191) that runs in the background. Receives approve/deny/focus commands from your phone and acts on them via AppleScript.
- **`setup.sh`** — installs both scripts, generates a secret token, registers the server as a macOS LaunchAgent, and wires the hooks into `~/.claude/settings.json`.

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.$(whoami).claude-focus-server.plist
rm ~/Library/LaunchAgents/com.$(whoami).claude-focus-server.plist
rm -rf ~/.claude/hooks/notify.py ~/.claude/hooks/focus_server.py ~/.claude/hooks/.server_token
```

Then remove the `hooks` block from `~/.claude/settings.json`.
