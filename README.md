# DiscordProxChatGmod

Python Discord bot + Garry's Mod TTT addon for proximity chat via Discord voice channel moves and server mute/deafen.

## Components
- Python bot (discord.py + aiohttp): receives events from GMod, maintains round state, clusters players, and performs Discord voice actions.
- GMod addon (Lua, server-side): emits TTT events and periodic player positions to the bot via HTTP.

## Quick start (Windows, self-hosted AMP)
1) Create a Discord application and bot; invite with intents: Guilds, Guild Members, and Voice States.
2) Copy `.env.sample` to `.env` and fill values.
3) Install Python 3.11+ and dependencies, then run the bot.

```powershell
# create venv (optional)
py -3.11 -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# run
python -m bot
```

## GMod addon
- Place `addons/discord_prox_chat` into your server's `garrysmod/addons/`.
- Configure ConVars (bridge URL/secret) in `sv_discord_prox_chat.lua` or via server cfg.
- Add to Workshop collection for AMP deployment (include `workshop.json` when publishing).

## Config
- Env vars: `DISCORD_TOKEN, GUILD_ID, LIVING_CHANNEL_ID, DEAD_CHANNEL_ID, BRIDGE_HOST, BRIDGE_PORT, BRIDGE_SECRET`.
- Optional mapping file under `config/mapping.json` for SteamID64 -> Discord user ID.
 - Proximity tuning: `PROX_RADIUS` (default 800 units), `PROX_MAX_CLUSTERS` (default 10), `PROX_CHANNEL_PREFIX` (default `Cluster`), optional `PROX_CATEGORY_ID` to contain channels.

### AMP (CubeCoders) notes
- Run the Python bot as a custom service under AMP on the same host as the GMod instance or reachable via network.
- Ensure AMP's firewall/port rules allow inbound HTTP from the GMod server to `BRIDGE_PORT`.
- Add `addons/discord_prox_chat` to your server content and include it in your Workshop collection; set `proxchat_bridge_url` to the bot's URL.

## Notes
- Discord bots cannot change per-user playback volume; proximity is simulated by channel membership and mute/deafen.
- Position updates should be modest (2–5 Hz) and batched to reduce churn.
 - Default PROX_RADIUS=800 Source units is a reasonable starting point (~66 feet). Increase if clusters are too fragmented; decrease if they’re too broad.