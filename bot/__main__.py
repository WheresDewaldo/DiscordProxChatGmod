from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional, Dict

import discord
from discord import app_commands

from .config import get_settings
from .http_server import create_app, run_server
from .discord_actions import ensure_in_channel, set_voice_policy
from .proximity import Pos, cluster_positions, ensure_cluster_channels, cleanup_cluster_channels
from .store import load_mapping, save_mapping
import secrets
import time


class ProxBot(discord.Client):
    def __init__(self, guild_id: int, living_channel: int, dead_channel: int,
                 prox_radius: float, max_clusters: int, prefix: str, category_id: int | None):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.voice_states = True
        super().__init__(intents=intents)
        self.guild_id = guild_id
        self.living_channel = living_channel
        self.dead_channel = dead_channel
        self._guild: Optional[discord.Guild] = None
        self.steam_to_discord: Dict[str, int] = {}
        self._pending_codes: Dict[str, tuple[int, float]] = {}  # code -> (discord_id, expiry_ts)
        self.prox_radius = prox_radius
        self.max_clusters = max_clusters
        self.cluster_prefix = prefix
        self.cluster_category_id = category_id
        # Hysteresis state
        self._last_cluster: Dict[int, int] = {}  # user_id -> cluster_index
        self._stable_count: Dict[int, int] = {}
        self._last_move_ts: Dict[int, float] = {}
        # Permission/cache flags
        self._perm_warned = False
        self._can_manage_channels = False
        self._can_move_members = False
        self._can_mute_members = False
        # Not-ready log rate limit
        self._not_ready_last_log_ts = 0.0
        # Slash commands
        self.tree = app_commands.CommandTree(self)

    def _refresh_perms(self) -> None:
        try:
            if not self._guild:
                return
            me = self.guild.me  # type: ignore
            if not me:
                return
            perms = me.guild_permissions
            before = (self._can_manage_channels, self._can_move_members, self._can_mute_members)
            self._can_manage_channels = bool(perms.manage_channels)
            self._can_move_members = bool(perms.move_members)
            self._can_mute_members = bool(perms.mute_members or perms.deafen_members)
            after = (self._can_manage_channels, self._can_move_members, self._can_mute_members)
            # If permissions improved, clear warn flag so we can log future issues if they regress
            if after > before and self._perm_warned and (self._can_manage_channels and self._can_move_members):
                self._perm_warned = False
        except Exception:
            pass

    @property
    def guild(self) -> discord.Guild:
        assert self._guild is not None
        return self._guild

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        # Try to resolve configured guild
        try:
            g = self.get_guild(self.guild_id)
            if g is None:
                g = await self.fetch_guild(self.guild_id)
            self._guild = g
            print(f"[ProxBot] Connected to guild={self.guild.name} ({self.guild.id})")
        except Exception as e:
            self._guild = None
            print(
                f"[ProxBot] Logged in but cannot access configured GUILD_ID={self.guild_id}: {e}. "
                f"Ensure the bot is invited to that server and GUILD_ID is correct. Will retry."
            )
            # Start a background retry to obtain guild later
            async def retry_guild():
                while self.is_ready() and self._guild is None:
                    try:
                        g2 = self.get_guild(self.guild_id) or await self.fetch_guild(self.guild_id)
                        if g2:
                            self._guild = g2
                            print(f"[ProxBot] Guild resolved after retry: {self.guild.name} ({self.guild.id})")
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(15)
            asyncio.create_task(retry_guild())
        # Snapshot permissions for the bot member
        try:
            me = self.guild.me or await self.guild.fetch_member(self.user.id)  # type: ignore
            perms = me.guild_permissions if me else None
            if perms:
                self._can_manage_channels = bool(perms.manage_channels)
                self._can_move_members = bool(perms.move_members)
                self._can_mute_members = bool(perms.mute_members or perms.deafen_members)
                print(
                    f"[ProxBot] Bot perms: manage_channels={self._can_manage_channels} "
                    f"move_members={self._can_move_members} mute/deafen={self._can_mute_members}"
                )
        except Exception:
            pass
        # Ready

    async def setup_hook(self) -> None:
        # Define slash commands here so they bind to this instance
        guild_obj = discord.Object(id=self.guild_id)

        @self.tree.command(name="linksteam", description="Generate a one-time code to link your SteamID from in-game", guild=guild_obj)
        async def linksteam(interaction: discord.Interaction):
            # Immediate ack to avoid 3s timeout
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            try:
                code = secrets.token_hex(3).upper()  # 6 hex chars
                self._pending_codes[code] = (interaction.user.id, time.time() + 300)  # 5 minutes
                msg = (
                    f"Your link code: {code}\n"
                    f"In Garry's Mod chat, type: !link {code}"
                )
                await interaction.edit_original_response(content=msg)
            except Exception as e:
                print(f"/linksteam error: {e}")
                # Fallback DM in case followup fails
                try:
                    await interaction.user.send("Here's your link code via DM: " + msg)
                except Exception:
                    pass

        @self.tree.command(name="linked", description="List currently linked SteamIDs (admin only)", guild=guild_obj)
        async def linked(interaction: discord.Interaction):
            # Immediate ack to avoid 3s timeout
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            try:
                # Admin gate: require Manage Guild
                perms = getattr(interaction.user, "guild_permissions", None)
                if not perms or not perms.manage_guild:
                    await interaction.edit_original_response(content="You need the Manage Server permission to use this.")
                    return
                if not self.steam_to_discord:
                    await interaction.edit_original_response(content="No links yet.")
                    return
                # Build a compact list (limit to 50 entries inline)
                items = list(self.steam_to_discord.items())
                lines = []
                limit = 50
                for i, (steamid, uid) in enumerate(items[:limit], start=1):
                    lines.append(f"{i}. {steamid} -> <@{uid}>")
                body = "\n".join(lines)
                footer = ""
                if len(items) > limit:
                    footer = f"\n… and {len(items) - limit} more."
                await interaction.edit_original_response(content=f"Linked players ({len(items)} total):\n{body}{footer}")
            except Exception as e:
                print(f"/linked error: {e}")
                try:
                    await interaction.user.send("An error occurred while listing links. Try again later.")
                except Exception:
                    pass

        @self.tree.error
        async def on_app_command_error(interaction: discord.Interaction, error: Exception):
            print(f"App command error: {error}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)
                await interaction.edit_original_response(content="Sorry, something went wrong handling that command.")
            except Exception:
                pass

        # Sync commands to this guild for instant availability
        try:
            synced = await self.tree.sync(guild=guild_obj)
            print(f"Synced {len(synced)} app commands to guild {self.guild_id}")
        except Exception as e:
            print(f"Slash command sync failed: {e}")

    def load_mapping(self, mapping_file: Optional[str]):
        if not mapping_file:
            return
        p = Path(mapping_file)
        if not p.exists():
            return
        self.steam_to_discord = load_mapping(str(p))
        print(f"Loaded {len(self.steam_to_discord)} ID mappings from {mapping_file}")

    def save_mapping(self, mapping_file: Optional[str]):
        if not mapping_file:
            return
        save_mapping(mapping_file, self.steam_to_discord)

    async def handle_event(self, ev: dict):
        # Determine event type early
        t = ev.get("type")
        # Process linking even before guild is ready (doesn't require guild)
        if t == "link_attempt":
            try:
                code_raw = ev.get("code")
                player = ev.get("player", {})
                steamid = player.get("steamid64")
                code = str(code_raw).strip().upper() if code_raw is not None else None
                if not code or not steamid:
                    print(f"[Link] Invalid link_attempt payload: code={code_raw!r} steamid={steamid!r}")
                    return {"linked": False, "reason": "invalid_payload"}
                entry = self._pending_codes.get(code)
                if not entry:
                    print(f"[Link] Code not found: {code} from steamid {steamid}")
                    return {"linked": False, "reason": "code_not_found"}
                discord_id, expiry = entry
                now_ts = time.time()
                if now_ts > expiry:
                    print(f"[Link] Code expired: {code} for discord {discord_id}")
                    del self._pending_codes[code]
                    return {"linked": False, "reason": "code_expired"}
                # Link and persist
                self.steam_to_discord[str(steamid)] = int(discord_id)
                del self._pending_codes[code]
                self.save_mapping(get_settings().MAPPING_FILE)
                print(f"[Link] Linked steamid {steamid} -> discord {discord_id}")
                # DM the user if possible
                try:
                    user = await self.fetch_user(discord_id)
                    await user.send(f"Linked SteamID64 {steamid} to your Discord account.")
                except Exception:
                    pass
                return {"linked": True}
            except Exception as e:
                print(f"[Link] Exception handling link_attempt: {e}")
                return {"linked": False, "reason": "exception"}

        # For all other events, ignore until the Discord client is ready and guild is set
        if not getattr(self, "_guild", None):
            et = t if t is not None else "?"
            now_ts = time.time()
            if now_ts - self._not_ready_last_log_ts >= 5.0:
                print(f"[ProxBot] Received event '{et}' before bot ready; ignoring")
                self._not_ready_last_log_ts = now_ts
            return

        # From here on, guild-dependent events
        t = t
        # Refresh permissions to pick up mid-run role changes
        self._refresh_perms()
        
        if t == "player_death":
            player = ev.get("player", {})
            steamid = player.get("steamid64")
            if steamid and steamid in self.steam_to_discord:
                uid = self.steam_to_discord[steamid]
                print(f"[ProxBot] player_death for steamid={steamid} mapped uid={uid}")
                # Move to Dead channel and optionally server mute/deafen
                await ensure_in_channel(
                    self.guild,
                    uid,
                    self.dead_channel,
                    mute=get_settings().PROX_DEAD_MUTE,
                    deafen=get_settings().PROX_DEAD_DEAFEN,
                )
        elif t == "round_end":
            # Return all mapped users to the Living channel and clear deaf/mute
            for uid in list(self.steam_to_discord.values()):
                await ensure_in_channel(self.guild, uid, self.living_channel, mute=False, deafen=False)
            # Optional cleanup of empty cluster channels
            if self._can_manage_channels:
                await cleanup_cluster_channels(self.guild, self.cluster_prefix)
        elif t == "round_start":
            # Optional: move mapped users that are already in voice to Living (normalize state)
            if get_settings().PROX_MOVE_TO_LIVING_ON_START:
                for uid in list(self.steam_to_discord.values()):
                    await ensure_in_channel(self.guild, uid, self.living_channel)
        elif t == "player_pos_batch":
            # Respect config toggle
            if not get_settings().PROX_ENABLE_CLUSTERING:
                return
            # Build a map of discord user -> last position
            positions = ev.get("positions") or []
            print(f"[ProxBot] player_pos_batch received with {len(positions)} positions")
            pts: Dict[int, Pos] = {}
            for item in positions:
                p = item.get("player", {})
                sid = p.get("steamid64")
                if not sid:
                    continue
                uid = self.steam_to_discord.get(sid)
                if not uid:
                    continue
                # Only track users who are in the guild (may not be in voice yet)
                member = self.guild.get_member(uid)
                if not member:
                    continue
                if not (member.voice and member.voice.channel):
                    # Not in voice; clustering won't move them. Skip but log at low frequency is excessive; keep quiet here.
                    continue
                pos = item.get("pos") or {}
                pts[uid] = Pos(float(pos.get("x", 0)), float(pos.get("y", 0)), float(pos.get("z", 0)))

            if not pts:
                # Nothing to do because no mapped users currently in voice
                return

            clusters = cluster_positions(pts, self.prox_radius, self.max_clusters)
            if not clusters:
                return

            # Ensure enough cluster channels exist (requires Manage Channels)
            if not self._can_manage_channels:
                if not self._perm_warned:
                    print("[ProxBot] Missing 'Manage Channels' permission; clustering disabled.")
                    self._perm_warned = True
                return
            try:
                print(f"[ProxBot] Ensuring {len(clusters)} cluster channels with prefix '{self.cluster_prefix}'")
                channels = await ensure_cluster_channels(self.guild, self.cluster_prefix, self.cluster_category_id, len(clusters))
            except Exception as e:
                if not self._perm_warned:
                    print(f"[ProxBot] Could not create/ensure cluster channels: {e}")
                    self._perm_warned = True
                return

            # Build reverse lookup: user -> cluster_index
            user_to_cluster: Dict[int, int] = {}
            for idx, members in enumerate(clusters):
                for uid in members:
                    user_to_cluster[uid] = idx

            # Hysteresis and throttling
            now = time.time()
            stability_needed = get_settings().PROX_STABILITY_BATCHES
            min_interval = get_settings().PROX_MIN_MOVE_INTERVAL_SEC

            # Move users that stabilized into a cluster and passed min interval
            for uid, cidx in user_to_cluster.items():
                prev = self._last_cluster.get(uid)
                if prev == cidx:
                    self._stable_count[uid] = self._stable_count.get(uid, 0) + 1
                else:
                    self._last_cluster[uid] = cidx
                    self._stable_count[uid] = 1
                last_move = self._last_move_ts.get(uid, 0.0)
                if self._stable_count[uid] >= stability_needed and (now - last_move) >= min_interval:
                    if cidx < len(channels):
                        if not self._can_move_members:
                            if not self._perm_warned:
                                print("[ProxBot] Missing 'Move Members' permission; cannot move users between channels.")
                                self._perm_warned = True
                            continue
                        print(f"[ProxBot] Moving uid={uid} to {channels[cidx].name}")
                        await ensure_in_channel(self.guild, uid, channels[cidx].id)
                        self._last_move_ts[uid] = now
        else:
            # Unknown event type ignored
            pass


async def main():
    settings = get_settings()
    bot = ProxBot(
        settings.GUILD_ID,
        settings.LIVING_CHANNEL_ID,
        settings.DEAD_CHANNEL_ID,
        settings.PROX_RADIUS,
        settings.PROX_MAX_CLUSTERS,
        settings.PROX_CHANNEL_PREFIX,
        settings.PROX_CATEGORY_ID,
    )
    bot.load_mapping(settings.MAPPING_FILE)

    app = create_app(settings.BRIDGE_SECRET, bot.handle_event)

    # run discord client and http server concurrently
    async def run_bot():
        await bot.start(settings.DISCORD_TOKEN)

    async def run_http():
        await run_server(settings.BRIDGE_HOST, settings.BRIDGE_PORT, app)

    await asyncio.gather(run_bot(), run_http())


if __name__ == "__main__":
    asyncio.run(main())