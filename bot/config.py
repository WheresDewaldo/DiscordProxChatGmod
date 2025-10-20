from __future__ import annotations

import os
from pydantic import BaseModel
from dotenv import load_dotenv


class Settings(BaseModel):
    DISCORD_TOKEN: str
    GUILD_ID: int
    LIVING_CHANNEL_ID: int
    DEAD_CHANNEL_ID: int

    BRIDGE_HOST: str = "0.0.0.0"
    BRIDGE_PORT: int = 8085
    BRIDGE_SECRET: str

    MAPPING_FILE: str | None = None

    # Proximity behavior
    PROX_ENABLE_CLUSTERING: bool = True
    PROX_RADIUS: float = 800.0  # Source engine units (~800 ~= ~66 ft)
    PROX_MAX_CLUSTERS: int = 10
    PROX_CHANNEL_PREFIX: str = "Cluster"
    PROX_CATEGORY_ID: int | None = None  # Optional voice category to place cluster channels
    PROX_STABILITY_BATCHES: int = 3  # require N consecutive batches in same cluster before move
    PROX_MIN_MOVE_INTERVAL_SEC: float = 5.0  # per-user min interval between moves
    # Cleanup policy: whether to delete empty cluster channels on round_end
    PROX_CLEANUP_CLUSTERS: bool = False
    # Optional: static list of cluster channel IDs (comma-separated) to use instead of dynamic creation
    PROX_CLUSTER_STATIC_IDS: str | None = None

    # Death handling
    PROX_DEAD_MUTE: bool = True
    PROX_DEAD_DEAFEN: bool = True
    # Optional: at round start, move mapped users (in voice) to Living channel
    PROX_MOVE_TO_LIVING_ON_START: bool = False
    # Fast move mode: when enabled, users will be moved on the first observed cluster change
    # instead of waiting for PROX_STABILITY_BATCHES consecutive batches. Useful when using
    # static cluster channels and wanting snappier movement. Still respects PROX_MIN_MOVE_INTERVAL_SEC.
    PROX_FAST_MOVE_ON_CHANGE: bool = False
    # Per-cluster cooldown: minimum time (seconds) before moving another user into the same cluster
    # to prevent rapid oscillation. Helps smooth movement in fast-move mode.
    PROX_CLUSTER_COOLDOWN_SEC: float = 1.5


def get_settings() -> Settings:
    # Load .env if present
    load_dotenv(override=False)
    env = {k: v for k, v in os.environ.items()}
    return Settings(**env)