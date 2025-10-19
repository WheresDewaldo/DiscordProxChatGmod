import os
import json
import sys
import urllib.request

BASE = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8080")
SECRET = os.environ.get("BRIDGE_SECRET", "")

def post(path: str, payload: dict):
    url = BASE.rstrip("/") + path
    req = urllib.request.Request(url, method="POST")
    req.add_header("Content-Type", "application/json")
    if SECRET:
        req.add_header("x-bridge-secret", SECRET)
    data = json.dumps(payload).encode("utf-8")
    with urllib.request.urlopen(req, data=data, timeout=3) as resp:
        print(resp.status, resp.read().decode("utf-8"))

if __name__ == "__main__":
    ev = {
        "type": "player_death",
        "ts": 1.0,
        "player": {"steamid64": "76561198000000000"}
    }
    if len(sys.argv) > 1:
        ev["type"] = sys.argv[1]
    post("/events", ev)