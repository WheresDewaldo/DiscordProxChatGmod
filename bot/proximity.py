from __future__ import annotations

from dataclasses import dataclass
import time
import asyncio
from typing import Optional, List
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


_creation_tasks: dict[str, asyncio.Task] = {}
_last_attempt: dict[str, float] = {}


async def _create_channel(guild, name: str, *, category_id: Optional[int] = None):
    """Background create of a voice channel; logs results and handles fallback."""
    TIMEOUT = 10.0  # seconds per Discord API operation to avoid indefinite hangs
    kwargs = {}
    cat_ok = False
    if category_id:
        cat = guild.get_channel(category_id)
        try:
            import discord  # type: ignore
            if cat and isinstance(cat, discord.CategoryChannel):
                kwargs["category"] = cat
                cat_ok = True
                try:
                    print(f"[ProxBot] ensure_cluster_channels(bg): using category '{cat.name}' ({category_id}) for '{name}'")
                except Exception:
                    pass
            else:
                print(f"[ProxBot] WARN: PROX_CATEGORY_ID={category_id} not a category; creating '{name}' at root.")
        except Exception:
            pass
    try:
        ch = await asyncio.wait_for(
            guild.create_voice_channel(name, **kwargs, reason="ProxChat create cluster"),
            timeout=TIMEOUT,
        )
        print(f"[ProxBot] Created voice channel '{ch.name}' (id={ch.id})" + (f" in category '{kwargs['category'].name}'" if cat_ok else ""))
        return ch
    except Exception as e:
        if kwargs:
            try:
                ch = await asyncio.wait_for(
                    guild.create_voice_channel(name, reason="ProxChat create cluster (fallback)"),
                    timeout=TIMEOUT,
                )
                print(f"[ProxBot] Created voice channel '{ch.name}' at guild root (fallback)")
                # If a category was desired, attempt to move it into that category now
                if category_id:
                    try:
                        cat = guild.get_channel(category_id)
                        import discord  # type: ignore
                        if cat and isinstance(cat, discord.CategoryChannel):
                            await asyncio.wait_for(
                                ch.edit(category=cat, reason="ProxChat move to category after fallback create"),
                                timeout=TIMEOUT,
                            )
                            print(f"[ProxBot] Moved '{ch.name}' into category '{cat.name}' after fallback create")
                    except Exception as e3:
                        print(f"[ProxBot] WARN: Could not move '{ch.name}' into category: {e3}")
                return ch
            except Exception as e2:
                print(f"[ProxBot] ERROR: Failed to create cluster channel '{name}': {e2}")
                # Last resort: clone an existing channel (e.g., '{prefix}-1') if present
                try:
                    prefix = name.split("-")[0]
                    template_name = f"{prefix}-1"
                    template = next((vc for vc in guild.voice_channels if vc.name == template_name), None)
                    if template is not None:
                        cloned = await asyncio.wait_for(
                            template.clone(name=name, reason="ProxChat clone fallback for cluster"),
                            timeout=TIMEOUT,
                        )
                        print(f"[ProxBot] Cloned '{template.name}' to '{cloned.name}' as fallback")
                        if category_id:
                            try:
                                cat = guild.get_channel(category_id)
                                import discord  # type: ignore
                                if cat and isinstance(cat, discord.CategoryChannel):
                                    await asyncio.wait_for(
                                        cloned.edit(category=cat, reason="ProxChat move cloned channel to category"),
                                        timeout=TIMEOUT,
                                    )
                                    print(f"[ProxBot] Moved cloned '{cloned.name}' into category '{cat.name}'")
                            except Exception as e4:
                                print(f"[ProxBot] WARN: Could not move cloned '{cloned.name}' into category: {e4}")
                        return cloned
                except Exception as e5:
                    print(f"[ProxBot] ERROR: Clone fallback failed for '{name}': {e5}")
                return None
        else:
            print(f"[ProxBot] ERROR: Failed to create cluster channel '{name}': {e}")
            return None


async def ensure_cluster_channels(
    guild, prefix: str, category_id: int | None, count: int
):
    # Channels the bot can see
    existing = [ch for ch in guild.voice_channels if ch.name.startswith(prefix)]
    try:
        names = ", ".join([f"{ch.name}({ch.id})" for ch in existing]) or "<none>"
        print(f"[ProxBot] ensure_cluster_channels: found {len(existing)} existing for prefix '{prefix}': {names}")
    except Exception:
        pass
    # Deterministically ensure names prefix-1..prefix-count exist
    existing_by_name = {ch.name: ch for ch in existing}
    # Determine missing desired names and schedule background creates
    for i in range(1, count + 1):
        name = f"{prefix}-{i}"
        if name in existing_by_name:
            continue
        now = time.time()
        last = _last_attempt.get(name, 0)
        if now - last < 15:
            try:
                print(f"[ProxBot] ensure_cluster_channels: skipping create for '{name}' (last attempt {int(now-last)}s ago)")
            except Exception:
                pass
            continue
        _last_attempt[name] = now
        if name in _creation_tasks and not _creation_tasks[name].done():
            # Already creating
            continue
        try:
            print(f"[ProxBot] ensure_cluster_channels: creating missing '{name}' (target count={count}, have={len(existing_by_name)})")
        except Exception:
            pass
        # Fire-and-forget background creation; do not block event processing
        _creation_tasks[name] = asyncio.create_task(_create_channel(guild, name, category_id=category_id))
    # Refresh list (only channels the bot can see)
    existing = [ch for ch in guild.voice_channels if ch.name.startswith(prefix)]
    existing.sort(key=lambda c: c.name)
    try:
        names = ", ".join([f"{ch.name}({ch.id})" for ch in existing]) or "<none>"
        print(f"[ProxBot] ensure_cluster_channels: returning first {min(len(existing), count)}: {names}")
    except Exception:
        pass
    return existing[:count]


async def create_cluster_channels(
    guild, prefix: str, category_id: int | None, count: int
) -> List:
    """Synchronously ensure up to 'count' cluster channels exist, returning the list of channels created in this call."""
    created: List = []
    # Refresh existing
    existing = {ch.name: ch for ch in guild.voice_channels if ch.name.startswith(prefix)}
    for i in range(1, count + 1):
        name = f"{prefix}-{i}"
        if name in existing:
            continue
        ch = await _create_channel(guild, name, category_id=category_id)
        if ch:
            created.append(ch)
            existing[name] = ch
    return created


async def cleanup_cluster_channels(guild, prefix: str, *, category_id: int | None = None, exclude_ids: set[int] | None = None) -> int:
    # Only delete empty channels with our prefix, optionally scoped to a category, and not in the exclude list
    exclude_ids = exclude_ids or set()
    deleted = 0
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
                deleted += 1
            except Exception as e:
                print(f"[ProxBot] WARN: Failed to delete cluster channel '{ch.name}': {e}")
    return deleted