from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict, Optional


EventType = Literal[
    "round_start",
    "round_end",
    "player_spawn",
    "player_death",
    "player_pos_batch",
]


class PlayerId(TypedDict):
    steamid64: str
    discord_id: Optional[int]


class Vec3(TypedDict):
    x: float
    y: float
    z: float


class PlayerPos(TypedDict):
    player: PlayerId
    pos: Vec3
    ts: float


class Event(TypedDict, total=False):
    type: EventType
    round_id: str
    player: PlayerId
    victim: PlayerId
    ts: float
    positions: list[PlayerPos]


@dataclass
class RoundState:
    active: bool = False
    round_id: Optional[str] = None


@dataclass
class PlayerState:
    steamid64: str
    discord_id: Optional[int]
    alive: bool = True
    last_pos: Optional[Vec3] = None