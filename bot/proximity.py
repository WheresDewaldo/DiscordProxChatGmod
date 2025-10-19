from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class Pos:
    x: float
    y: float
    z: float


def dist2(a: Pos, b: Pos) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    dz = a.z - b.z
    return dx * dx + dy * dy + dz * dz


def cluster_positions(
    points: Dict[int, Pos], radius: float, max_clusters: int
) -> List[List[int]]:
    # Simple greedy clustering: iterate points, assign to existing cluster if within radius of any member, else new cluster.
    r2 = radius * radius
    clusters: List[List[int]] = []
    for uid, p in points.items():
        placed = False
        for c in clusters:
            # check against first member as centroid proxy
            ref = points[c[0]]
            if dist2(p, ref) <= r2:
                c.append(uid)
                placed = True
                break
        if not placed:
            if len(clusters) >= max_clusters:
                # Put into the last cluster to avoid creating more channels
                clusters[-1].append(uid) if clusters else clusters.append([uid])
            else:
                clusters.append([uid])
    return clusters


async def ensure_cluster_channels(
    guild, prefix: str, category_id: int | None, count: int
):
    existing = [ch for ch in guild.voice_channels if ch.name.startswith(prefix)]
    # Create missing
    for i in range(len(existing) + 1, count + 1):
        kwargs = {}
        if category_id:
            cat = guild.get_channel(category_id)
            if cat:
                kwargs["category"] = cat
        await guild.create_voice_channel(f"{prefix}-{i}", **kwargs, reason="ProxChat create cluster")
    # Refresh list
    existing = [ch for ch in guild.voice_channels if ch.name.startswith(prefix)]
    # Return the first 'count' channels in deterministic order
    existing.sort(key=lambda c: c.name)
    return existing[:count]


async def cleanup_cluster_channels(guild, prefix: str):
    for ch in list(guild.voice_channels):
        if ch.name.startswith(prefix) and len(ch.members) == 0:
            try:
                await ch.delete(reason="ProxChat cleanup")
            except Exception:
                pass