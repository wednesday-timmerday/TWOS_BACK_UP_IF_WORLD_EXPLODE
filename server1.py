"""
broadcast_server.py  —  Run this on your SERVER PC.

Install deps:  pip install flask
Then run:      python broadcast_server.py

Open http://<your-server-ip>:5050 in a browser,
type a message, hit Send — every connected game client
will pop a Windows message box.
"""

import time

from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

# Stores pending messages as {id, text, timestamp}
_messages: list[dict] = []
_next_id: int = 1

# ── Web page ──────────────────────────────────────────────────────────────────
PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>TWoS Broadcast</title>
  <style>
    body { background:#111; color:#eee; font-family:Segoe UI,sans-serif;
           display:flex; flex-direction:column; align-items:center;
           justify-content:center; min-height:100vh; margin:0; }
    h1   { color:#f5c842; margin-bottom:24px; }
    .box { background:#1e1e1e; border:1px solid #333; border-radius:10px;
           padding:32px; width:480px; }
    textarea { width:100%; height:100px; background:#252525; color:#eee;
               border:1px solid #555; border-radius:6px; padding:10px;
               font-size:15px; resize:vertical; box-sizing:border-box; }
    button { margin-top:12px; width:100%; padding:12px;
             background:#f5c842; color:#111; font-size:16px; font-weight:bold;
             border:none; border-radius:6px; cursor:pointer; }
    button:hover { background:#ffe066; }
    #status { margin-top:14px; font-size:13px; color:#888; text-align:center; }
    #log    { margin-top:20px; max-height:220px; overflow-y:auto;
              background:#161616; border-radius:6px; padding:10px;
              font-size:13px; color:#aaa; }
    .entry  { border-bottom:1px solid #2a2a2a; padding:5px 0; }
    .ts     { color:#555; font-size:11px; }
  </style>
</head>
<body>
  <h1>🕯 The Weight of Shadows — Broadcast</h1>
  <div class="box">
    <textarea id="msg" placeholder="Type your announcement here..."></textarea>
    <button onclick="send()">Send to all players</button>
    <div id="status">Ready.</div>
    <div id="log"></div>
  </div>
  <script>
    async function send() {
      const text = document.getElementById('msg').value.trim();
      if (!text) return;
      const res = await fetch('/broadcast', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({message: text})
      });
      const data = await res.json();
      document.getElementById('status').textContent =
        data.ok ? `✅ Sent to ${data.clients} client(s)` : '❌ Error';
      document.getElementById('msg').value = '';
      loadLog();
    }

    async function loadLog() {
      const res = await fetch('/history');
      const data = await res.json();
      const log = document.getElementById('log');
      log.innerHTML = data.messages.slice().reverse().map(m =>
        `<div class="entry"><span class="ts">${m.time}</span><br>${m.text}</div>`
      ).join('');
    }

    document.getElementById('msg').addEventListener('keydown', e => {
      if (e.key === 'Enter' && e.ctrlKey) send();
    });

    loadLog();
    setInterval(loadLog, 5000);
  </script>
</body>
</html>
"""

# ── Routes ────────────────────────────────────────────────────────────────────


@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/broadcast", methods=["POST"])
def broadcast():
    global _next_id
    data = request.get_json(force=True)
    text = (data.get("message") or "").strip()
    if not text:
        return jsonify(ok=False, error="empty message"), 400

    entry = {
        "id": _next_id,
        "text": text,
        "timestamp": time.time(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _messages.append(entry)
    _next_id += 1

    # Keep last 100 messages only
    if len(_messages) > 100:
        _messages.pop(0)

    print(f"[BROADCAST] #{entry['id']}: {text}")
    return jsonify(ok=True, id=entry["id"], clients="all")


@app.route("/poll")
def poll():
    """
    Game clients call GET /poll?since=<last_id>
    Returns all messages with id > since.
    """
    try:
        since = int(request.args.get("since", 0))
    except ValueError:
        since = 0
    new = [m for m in _messages if m["id"] > since]
    return jsonify(messages=new)


@app.route("/history")
def history():
    return jsonify(messages=_messages[-50:])


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TWoS Broadcast Server starting on port 5050")
    print("Open http://<this-pc-ip>:5050 in your browser")
    app.run(host="0.0.0.0", port=5050, debug=False)
