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
    # Channels the bot can see
    existing = [ch for ch in guild.voice_channels if ch.name.startswith(prefix)]
    # Create missing
    for i in range(len(existing) + 1, count + 1):
        name = f"{prefix}-{i}"
        kwargs = {}
        cat_ok = False
        if category_id:
            cat = guild.get_channel(category_id)
            # Only attach if it's a category the bot can access
            try:
                import discord  # type: ignore
                if cat and isinstance(cat, discord.CategoryChannel):
                    kwargs["category"] = cat
                    cat_ok = True
                else:
                    print(f"[ProxBot] WARN: PROX_CATEGORY_ID={category_id} does not resolve to a category; creating '{name}' at guild root.")
            except Exception:
                pass
        try:
            ch = await guild.create_voice_channel(name, **kwargs, reason="ProxChat create cluster")
            print(f"[ProxBot] Created voice channel '{ch.name}' (id={ch.id})" + (f" in category '{kwargs['category'].name}'" if cat_ok else ""))
        except Exception as e:
            # Fallback: try without category
            if kwargs:
                try:
                    ch = await guild.create_voice_channel(name, reason="ProxChat create cluster (fallback)")
                    print(f"[ProxBot] Created voice channel '{ch.name}' at guild root (fallback)")
                except Exception as e2:
                    print(f"[ProxBot] ERROR: Failed to create cluster channel '{name}': {e2}")
                    break
            else:
                print(f"[ProxBot] ERROR: Failed to create cluster channel '{name}': {e}")
                break
    # Refresh list (only channels the bot can see)
    existing = [ch for ch in guild.voice_channels if ch.name.startswith(prefix)]
    existing.sort(key=lambda c: c.name)
    return existing[:count]


async def cleanup_cluster_channels(guild, prefix: str, *, category_id: int | None = None, exclude_ids: set[int] | None = None):
    # Only delete empty channels with our prefix, optionally scoped to a category, and not in the exclude list
    exclude_ids = exclude_ids or set()
    for ch in list(guild.voice_channels):
        if not ch.name.startswith(prefix):
            continue
        if ch.id in exclude_ids:
            continue
        if category_id is not None and getattr(ch, "category_id", None) != category_id:
            continue
        if len(ch.members) == 0:
            try:
                await ch.delete(reason="ProxChat cleanup")
                print(f"[ProxBot] Deleted empty cluster channel '{ch.name}' (id={ch.id})")
            except Exception as e:
                print(f"[ProxBot] WARN: Failed to delete cluster channel '{ch.name}': {e}")