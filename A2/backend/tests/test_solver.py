import random
from collections import deque

from app.cube.engine import MOVES, SOLVED, apply_move, apply_moves, is_solved
from app.cube.scramble import TEST_SETS, make_puzzle
from app.cube.solver import solve_optimal


def _distances(depth: int) -> dict[str, int]:
    dist = {SOLVED: 0}
    q = deque([SOLVED])
    while q:
        s = q.popleft()
        if dist[s] == depth:
            continue
        for m in MOVES:
            t = apply_move(s, m)
            if t not in dist:
                dist[t] = dist[s] + 1
                q.append(t)
    return dist


def test_matches_plain_bfs_distances():
    dist = _distances(3)
    rng = random.Random(7)
    for state, d in rng.sample(sorted(dist.items()), 400):
        r = solve_optimal(state)
        assert r.exact and r.distance == d
        assert is_solved(apply_moves(state, r.solution))


def test_solved_state():
    r = solve_optimal(SOLVED)
    assert r.distance == 0 and r.solution == []


def test_reports_unknown_beyond_depth():
    state = apply_moves(SOLVED, "R U F L D B")
    r = solve_optimal(state, max_depth=3)
    assert r.distance is None and not r.exact


def test_puzzles_are_reproducible_and_in_range():
    for ts, (lo, hi) in TEST_SETS.items():
        a, b = make_puzzle(ts, 3), make_puzzle(ts, 3)
        assert a.state == b.state and a.scramble == b.scramble
        assert lo <= len(a.scramble) <= hi
        assert apply_moves(SOLVED, a.scramble) == a.state


def test_primary_puzzles_have_exact_optimum():
    for seed in range(1, 11):
        p = make_puzzle("primary", seed)
        assert p.optimal_exact and 1 <= p.optimal_moves <= len(p.scramble)
        assert is_solved(apply_moves(p.state, p.optimal_solution))
        assert p.reference_moves == p.optimal_moves


def test_extension_uses_upper_bound():
    p = make_puzzle("extension", 1)
    assert p.optimal_moves is None and p.reference_moves == len(p.scramble)


def test_three_set_is_exactly_three_moves_away():
    for seed in range(1, 21):
        p = make_puzzle("three", seed)
        assert len(p.scramble) == 3 and p.optimal_exact and p.optimal_moves == 3
