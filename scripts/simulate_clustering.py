"""Offline benchmark: legacy greedy clustering vs. connected-components + stable labels.

Simulates TTT rounds (players wandering in groups that split/merge on a 6000x6000 map,
positions sampled at 4 Hz) and counts:
  * channel moves  - how often a player's assigned voice channel changes
  * missed pairs   - samples where two players within PROX_RADIUS were put in
                     different channels (i.e. standing next to someone you can't hear)

Run:  python -m scripts.simulate_clustering
"""
from __future__ import annotations

import math
import random
from typing import Dict, List

from bot.proximity import Pos, assign_stable_labels, cluster_positions, dist2

RADIUS = 800.0
MAX_CLUSTERS = 10
MAP = 6000.0


def legacy_cluster(points: Dict[int, Pos], radius: float, max_clusters: int) -> List[List[int]]:
    """Verbatim copy of the previous algorithm, kept here for comparison."""
    r2 = radius * radius
    clusters: List[List[int]] = []
    for uid, p in points.items():
        placed = False
        for c in clusters:
            if dist2(p, points[c[0]]) <= r2:
                c.append(uid)
                placed = True
                break
        if not placed:
            if len(clusters) >= max_clusters:
                clusters[-1].append(uid) if clusters else clusters.append([uid])
            else:
                clusters.append([uid])
    return clusters


def simulate_round(seed: int, players: int = 16, ticks: int = 4 * 180):
    rng = random.Random(seed)
    # Players start in a few spawn groups and follow drifting waypoints
    pos = {i: [rng.uniform(0, MAP), rng.uniform(0, MAP)] for i in range(players)}
    goal = {i: [rng.uniform(0, MAP), rng.uniform(0, MAP)] for i in range(players)}
    leader = {i: (i // 3) * 3 for i in range(players)}  # loose squads of 3
    frames = []
    for _ in range(ticks):
        for i in range(players):
            if rng.random() < 0.01:
                goal[i] = [rng.uniform(0, MAP), rng.uniform(0, MAP)]
            if rng.random() < 0.004:
                leader[i] = rng.randrange(players)
            tgt = goal[i] if leader[i] == i else [pos[leader[i]][0] + rng.uniform(-300, 300),
                                                  pos[leader[i]][1] + rng.uniform(-300, 300)]
            dx, dy = tgt[0] - pos[i][0], tgt[1] - pos[i][1]
            d = math.hypot(dx, dy) or 1
            step = min(d, 55.0)  # ~220 units/s at 4 Hz
            pos[i][0] += dx / d * step + rng.uniform(-15, 15)
            pos[i][1] += dy / d * step + rng.uniform(-15, 15)
        frames.append({i: Pos(p[0], p[1], 0.0) for i, p in pos.items()})
    return frames


def score(frames, mode: str, shuffle: bool = False):
    moves = missed = 0
    last: Dict[int, int] = {}
    labels_state: Dict[int, int] = {}
    order_rng = random.Random(0)
    for pts in frames:
        # shuffle=True models an unstable input order (legacy result depends on it; new one does not).
        items = list(pts.items())
        if shuffle:
            order_rng.shuffle(items)
        pts = dict(items)
        if mode == "legacy":
            clusters = legacy_cluster(pts, RADIUS, MAX_CLUSTERS)
            labels = list(range(len(clusters)))
        else:
            clusters = cluster_positions(pts, RADIUS, MAX_CLUSTERS, prev_labels=labels_state)
            labels = assign_stable_labels(clusters, labels_state)
        assign = {u: labels[i] for i, c in enumerate(clusters) for u in c}
        labels_state = assign
        for u, ch in assign.items():
            if u in last and last[u] != ch:
                moves += 1
        last = assign
        ids = sorted(pts)
        for a_i, a in enumerate(ids):
            for b in ids[a_i + 1:]:
                if dist2(pts[a], pts[b]) <= RADIUS * RADIUS and assign[a] != assign[b]:
                    missed += 1
    return moves, missed


def main() -> None:
    rounds = 25
    tot = {"legacy": [0, 0], "new": [0, 0]}
    for seed in range(rounds):
        frames = simulate_round(seed)
        for mode in tot:
            m, x = score(frames, mode)
            tot[mode][0] += m
            tot[mode][1] += x
    print(f"{rounds} simulated rounds, 16 players, 3 min @ 4 Hz\n")
    print(f"{'algorithm':<12}{'channel moves':>16}{'missed pairs':>16}")
    for mode, (m, x) in tot.items():
        print(f"{mode:<12}{m:>16,}{x:>16,}")
    lm, lx = tot["legacy"]
    nm, nx = tot["new"]
    print(f"\nchannel moves: {100 * (1 - nm / lm):.0f}% fewer   missed pairs: {100 * (1 - nx / max(lx, 1)):.0f}% fewer")


if __name__ == "__main__":
    main()
