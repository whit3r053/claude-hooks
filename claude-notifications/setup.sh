#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USERNAME=$(whoami)

echo ""
echo "Claude Code Notifications — setup"
echo "=================================="

# 1. Copy hook scripts (skip if already installed — don't overwrite customised versions)
mkdir -p ~/.claude/hooks
for f in notify.py focus_server.py; do
    if [ ! -f ~/.claude/hooks/$f ]; then
        cp "$SCRIPT_DIR/$f" ~/.claude/hooks/$f
        chmod +x ~/.claude/hooks/$f
        echo "✓ Installed ~/.claude/hooks/$f"
    else
        echo "✓ ~/.claude/hooks/$f already exists — skipping"
    fi
done

# 2. Generate server token (skip if already exists)
if [ ! -f ~/.claude/hooks/.server_token ]; then
    python3 -c "import secrets; print(secrets.token_hex(24))" > ~/.claude/hooks/.server_token
    chmod 600 ~/.claude/hooks/.server_token
    echo "✓ Server token generated"
else
    echo "✓ Server token already exists — keeping it"
fi

# 3. Install LaunchAgent (fills in your username)
PLIST_DEST="$HOME/Library/LaunchAgents/com.${USERNAME}.claude-focus-server.plist"
sed "s/YOUR_USERNAME/${USERNAME}/g" "$SCRIPT_DIR/com.YOURUSERNAME.claude-focus-server.plist.template" > "$PLIST_DEST"
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"
echo "✓ Focus server started (runs in background at login)"

# 4. Merge hooks into ~/.claude/settings.json
python3 - "$SCRIPT_DIR" <<'PYEOF'
import json, os, sys

script_dir = sys.argv[1]
settings_path = os.path.expanduser("~/.claude/settings.json")
hooks_path = os.path.join(script_dir, "settings-hooks-snippet.json")

try:
    with open(settings_path) as f:
        settings = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    settings = {}

with open(hooks_path) as f:
    snippet = json.load(f)

if "hooks" not in settings:
    settings["hooks"] = snippet["hooks"]
    os.makedirs(os.path.expanduser("~/.claude"), exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    print("✓ Hooks added to ~/.claude/settings.json")
else:
    print("✓ Hooks already present in settings.json — skipping")
PYEOF

# 5. Suggest a private ntfy topic
SUGGESTED_TOPIC="claude-${USERNAME}-$(python3 -c 'import secrets; print(secrets.token_hex(4))')"

echo ""
echo "Setup complete! Two manual steps left:"
echo ""
echo "  1. Pick a private ntfy topic and add it to ~/.zshrc:"
echo "     export NTFY_TOPIC=${SUGGESTED_TOPIC}"
echo ""
echo "  2. Install the ntfy app and subscribe to that topic:"
echo "     iOS:     https://apps.apple.com/app/ntfy/id1625396347"
echo "     Android: https://play.google.com/store/apps/details?id=io.heckel.ntfy"
echo ""
echo "Then open a new Claude Code session and you're live."
echo ""
