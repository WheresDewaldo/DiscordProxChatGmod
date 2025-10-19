# Copilot instructions for this repo

Goal: Discord bot that provides proximity chat behavior for Garry’s Mod TTT players in Discord (move members between channels based on proximity, move to Dead channel on death, return at round end, optional server mute/deafen policies).

Important constraint
- Discord bots cannot change other users’ playback volume. Proximity must be simulated by channel membership and mute/deafen, not per-user volume gain.

Big picture (planned components)
- Discord bot service (Node.js with discord.js or Python with discord.py). Responsibilities: track round state, cluster players by proximity, move members among voice channels, manage server mute/deafen as policy.
- GMod TTT addon (Lua): emits game events (round_start/end, player_spawn/death, periodic player_pos) to the bot via HTTP or WebSocket with a shared secret.
- Config/mapping: Discord guild/channel IDs and SteamID64 <-> Discord user ID mapping. Store secrets in env vars.

Data flow (high level)
- Lua addon ➜ Bot: JSON events with {type, player, pos, ts, round_id}. Frequency for player_pos should be low (e.g., 2–5 Hz) and batched if possible.
- Bot ➜ Discord: Voice state ops (move members to Living/Dead/Cluster-N channels), optionally create ephemeral Cluster-N channels per proximity group and clean them up at round end.

Conventions to follow here
- GMod addon layout: lua/** with cl_*, sv_*, sh_* files; keep server-to-bot network code in sv_*.lua.
- Event schema and policies documented under docs/ once added (e.g., docs/events.md, docs/policies.md). Version event schema if breaking changes.
- Configuration: use env vars DISCORD_TOKEN, GUILD_ID, LIVING_CHANNEL_ID, DEAD_CHANNEL_ID, BRIDGE_URL, BRIDGE_SECRET; persist non-secret IDs in config/*.json when code appears.

Developer workflows (current)
- Run bot locally (Windows/PowerShell):
	- Python 3.11+
	- Install deps from `requirements.txt`
	- Copy `.env.sample` ➜ `.env`, fill values
	- Start with `python -m bot`
- Run GMod addon: copy `addons/discord_prox_chat` into your server `garrysmod/addons/`; set ConVars `proxchat_bridge_url` and `proxchat_bridge_secret`; ensure TTT hooks fire.
- Tests: to be added; target event routing and Discord actions with mocked API.

Fast indexing checklist (now)
- README.md for setup steps and commands.
- `requirements.txt` for Python deps; `bot/` for source; `addons/discord_prox_chat/` for Lua.
- `addons/discord_prox_chat/workshop.json` for Workshop publishing metadata.

Guardrails for AI changes
- Don’t introduce extra services (e.g., custom voice relays) without explicit approval; first implement channel-based proximity.
- Keep event payloads backward compatible; add versioning if needed. Never commit tokens; use env/secret store.

Next steps
- If code exists elsewhere, sync it here and I will update this document with concrete paths and commands.
- If starting from scratch, ask once for preferred language (Node or Python) and deployment target, then scaffold minimally per above.