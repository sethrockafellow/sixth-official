"""A fake model server for tests: it speaks the OpenAI chat-completions format, so the real
Agent Framework tool loop runs against it with no Azure.

It plays a narrator that follows the rules: it calls get_event_context first, then answers
with a comment whose claims cite the tool result. With mode "wrong_first" its first answer
writes a wrong percent, to test the verifier's retry.
"""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"mode": "good", "calls": 0}


def _answer(messages):
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    user = next((m for m in reversed(messages) if m.get("role") == "user"), {})
    text = user.get("content") if isinstance(user.get("content"), str) else json.dumps(user.get("content"))
    is_retry = "failures" in (text or "")
    if not tool_msgs:
        eid = re.search(r'"event_id": "(e\d+)"', text or "").group(1)
        return {"role": "assistant", "content": None, "tool_calls": [{
            "id": "call_1", "type": "function",
            "function": {"name": "get_event_context", "arguments": json.dumps({"event_id": eid})}}]}
    ctx = json.loads(tool_msgs[-1]["content"] if isinstance(tool_msgs[-1]["content"], str)
                     else tool_msgs[-1]["content"][0]["text"])
    after, ev = ctx["state_after"], ctx["event"]
    wph = after["win_prob_home"]
    pct = round(wph * 100)
    if STATE["mode"] == "wrong_first" and not is_retry:
        pct = min(99, pct + 15)
    team = ev.get("team_name", "Home")
    claim = f"{pct}% chance to win"
    draft = {"text": f"{team} keep pushing, and the home side now have a {claim}.",
             "evidence": [{"claim": claim, "source": f"{after['snapshot_id']}.win_prob_home", "value": wph,
                           "unit": "probability", "label_metric": None}]}
    return {"role": "assistant", "content": json.dumps(draft)}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        STATE["calls"] += 1
        msg = _answer(body["messages"])
        out = {"id": "x", "object": "chat.completion", "created": 0, "model": body.get("model", "fake"),
               "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if msg.get("tool_calls") else "stop"}],
               "usage": {"prompt_tokens": 900, "completion_tokens": 60, "total_tokens": 960}}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start(port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
