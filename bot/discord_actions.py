from __future__ import annotations

import asyncio
from typing import Iterable, Optional

import discord


async def ensure_in_channel(
    guild: discord.Guild,
    user_id: int,
    channel_id: int,
    *,
    mute: Optional[bool] = None,
    deafen: Optional[bool] = None,
) -> None:
    try:
        member = guild.get_member(user_id) or await guild.fetch_member(user_id)
    except Exception:
        return
    # Can't force-connect users to voice; only move if already in a voice channel
    if not member or not member.voice or not member.voice.channel:
        return
    kwargs = {}
    if mute is not None:
        kwargs["mute"] = mute
    if deafen is not None:
        kwargs["deafen"] = deafen
    try:
        await member.move_to(guild.get_channel(channel_id), reason="ProxChat move")
    except Exception as e:
        # Missing permissions or hierarchy issue; ignore to avoid spam
        return
    if kwargs:
        try:
            await member.edit(**kwargs, reason="ProxChat voice policy")
        except Exception:
            pass


async def bulk_move(
    guild: discord.Guild,
    moves: Iterable[tuple[int, int]],
) -> None:
    # moves: [(user_id, channel_id)]
    tasks = [
        ensure_in_channel(guild, uid, cid) for uid, cid in moves
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def set_voice_policy(
    guild: discord.Guild, user_id: int, *, mute: Optional[bool] = None, deafen: Optional[bool] = None
) -> None:
    try:
        member = guild.get_member(user_id) or await guild.fetch_member(user_id)
    except Exception:
        return
    kwargs = {}
    if mute is not None:
        kwargs["mute"] = mute
    if deafen is not None:
        kwargs["deafen"] = deafen
    if kwargs:
        try:
            await member.edit(**kwargs, reason="ProxChat voice policy")
        except Exception:
            pass