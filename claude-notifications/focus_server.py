#!/usr/bin/env python3
# Token file is generated once at setup and never committed:
# python3 -c "import secrets; print(secrets.token_hex(24))" > ~/.claude/hooks/.server_token
# chmod 600 ~/.claude/hooks/.server_token
import http.server, subprocess, os, time

TOKEN_FILE = os.path.expanduser("~/.claude/hooks/.server_token")
PORT = 9191

with open(TOKEN_FILE) as f:
    SECRET = f.read().strip()

ACTIVATE_TERMINAL = """
tell application "System Events"
    set termApps to {"iTerm2", "iTerm", "Terminal"}
    repeat with appName in termApps
        if (name of processes) contains appName then
            tell application appName to activate
            exit repeat
        end if
    end repeat
end tell
"""

def send_key(char):
    subprocess.run(["osascript", "-e", ACTIVATE_TERMINAL], capture_output=True)
    time.sleep(0.4)
    subprocess.run(["osascript", "-e", f'tell application "System Events" to keystroke "{char}"'], capture_output=True)
    subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 36'], capture_output=True)

ROUTES = {
    "/focus":   lambda: subprocess.run(["osascript", "-e", ACTIVATE_TERMINAL], capture_output=True),
    "/approve": lambda: send_key("y"),
    "/deny":    lambda: send_key("n"),
}

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        action = ROUTES.get(self.path)
        if action is None:
            self.send_response(404); self.end_headers(); return
        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {SECRET}":
            self.send_response(403); self.end_headers(); return
        action()
        self.send_response(200); self.end_headers()
        self.wfile.write(b"ok")

httpd = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
httpd.serve_forever()
