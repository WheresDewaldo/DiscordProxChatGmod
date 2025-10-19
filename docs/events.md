# Event schema (Lua ➜ Bot)

All requests are HTTP POST to `/events` with header `x-bridge-secret: <secret>` and JSON body.

Common fields:
- type: string (see below)
- ts: number (seconds since map start; informational)
- round_id: string (optional, for correlation)

Events:
- round_start
  - { "type": "round_start", "ts": 123.4, "round_id": "169" }
- round_end
  - { "type": "round_end", "ts": 456.7 }
- player_spawn
  - { "type": "player_spawn", "ts": 10.2, "player": { "steamid64": "765611980..." } }
- player_death
  - { "type": "player_death", "ts": 20.5, "player": { "steamid64": "..." } }
- player_pos_batch
  - { "type": "player_pos_batch", "positions": [ { "player": { "steamid64": "..." }, "pos": { "x": 1, "y": 2, "z": 3 }, "ts": 30.0 } ] }

Notes:
- Position batches should be sent at 2–5 Hz.
- The bot maps SteamID64 to Discord user ID via `config/mapping.json` or other configured source.
- Proximity clustering and channel fan-out may be added later; keep payloads backward compatible.