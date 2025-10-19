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
    BRIDGE_PORT: int = 8080
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


def get_settings() -> Settings:
    # Load .env if present
    load_dotenv(override=False)
    env = {k: v for k, v in os.environ.items()}
    return Settings(**env)