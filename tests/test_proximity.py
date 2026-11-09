import random

from bot.proximity import Pos, assign_stable_labels, cluster_positions

R = 800.0


def groups(clusters):
    return sorted(sorted(c) for c in clusters)


def test_chain_of_players_is_one_group():
    # A-B and B-C are within radius, A-C is not: everyone can hear their neighbour, so one channel.
    pts = {1: Pos(0, 0, 0), 2: Pos(700, 0, 0), 3: Pos(1400, 0, 0)}
    assert groups(cluster_positions(pts, R, 10)) == [[1, 2, 3]]


def test_result_does_not_depend_on_input_order():
    rng = random.Random(7)
    pts = {i: Pos(rng.uniform(0, 4000), rng.uniform(0, 4000), 0) for i in range(24)}
    expected = groups(cluster_positions(pts, R, 10))
    for _ in range(20):
        items = list(pts.items())
        rng.shuffle(items)
        assert groups(cluster_positions(dict(items), R, 10)) == expected


def test_overflow_merges_closest_groups_not_last():
    pts = {1: Pos(0, 0, 0), 2: Pos(2000, 0, 0), 3: Pos(10000, 0, 0)}
    # Cap at 2: the two nearby groups merge; the far-away player stays alone.
    assert groups(cluster_positions(pts, R, 2)) == [[1, 2], [3]]


def test_hysteresis_keeps_pair_together_at_edge():
    pts = {1: Pos(0, 0, 0), 2: Pos(850, 0, 0)}  # just outside radius
    assert groups(cluster_positions(pts, R, 10)) == [[1], [2]]
    assert groups(cluster_positions(pts, R, 10, prev_labels={1: 0, 2: 0})) == [[1, 2]]
    far = {1: Pos(0, 0, 0), 2: Pos(1000, 0, 0)}  # beyond the sticky band
    assert groups(cluster_positions(far, R, 10, prev_labels={1: 0, 2: 0})) == [[1], [2]]


def test_labels_survive_other_groups_splitting():
    prev = {1: 0, 2: 0, 3: 1, 4: 1, 5: 2, 6: 2}
    # Group with label 0 splits; groups 1 and 2 must keep their channels.
    clusters = [[1], [2], [3, 4], [5, 6]]
    labels = assign_stable_labels(clusters, prev)
    by_cluster = dict(zip(map(tuple, clusters), labels))
    assert by_cluster[(3, 4)] == 1
    assert by_cluster[(5, 6)] == 2
    assert sorted(labels) == sorted(set(labels))  # unique
    assert {by_cluster[(1,)], by_cluster[(2,)]} == {0, 3}


def test_labels_bounded_by_cluster_count_on_fresh_state():
    assert assign_stable_labels([[1], [2], [3]]) == [0, 1, 2]
