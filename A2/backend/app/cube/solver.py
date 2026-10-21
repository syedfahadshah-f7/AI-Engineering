"""Exact shortest-solution search (half-turn metric).

Bidirectional breadth-first search: one frontier grows from the scrambled
state, the other from the solved state, and the search stops at the first
depth where they meet. BFS explores states in order of distance, so the first
meeting depth is the true optimum. It is complete for any distance up to
``max_depth``, and when nothing is found it proves the optimum is larger.

Both frontiers only reach about half the target depth, so a 5-move puzzle
costs roughly 2 * 18 * 15^2 states instead of 18 * 15^4.
"""

from __future__ import annotations

from dataclasses import dataclass

from .engine import MOVES, SOLVED, apply_move, inverse_move, is_solved

# Pairs of opposite faces commute; only expand them in one fixed order.
_OPPOSITE = {"U": "D", "D": "U", "R": "L", "L": "R", "F": "B", "B": "F"}
_ORDER = {f: i for i, f in enumerate("URFDLB")}


def _allowed_after(last: str | None, move: str) -> bool:
    if last is None:
        return True
    a, b = last[0], move[0]
    if a == b:
        return False
    if _OPPOSITE[a] == b and _ORDER[a] > _ORDER[b]:
        return False
    return True


@dataclass(frozen=True)
class OptimalResult:
    distance: int | None  # None = more than max_depth moves
    solution: list[str] | None
    exact: bool  # True when ``distance`` is proven optimal
    max_depth: int


def _expand(frontier: dict[str, tuple[str, ...]], seen: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    nxt: dict[str, tuple[str, ...]] = {}
    for state, path in frontier.items():
        last = path[-1] if path else None
        for m in MOVES:
            if not _allowed_after(last, m):
                continue
            s2 = apply_move(state, m)
            if s2 in seen or s2 in nxt:
                continue
            nxt[s2] = path + (m,)
    seen.update(nxt)
    return nxt


def solve_optimal(state: str, max_depth: int = 10) -> OptimalResult:
    """Return a provably shortest solution if one exists within ``max_depth``."""
    if is_solved(state):
        return OptimalResult(0, [], True, max_depth)

    # Paths from the start state (forward) and from SOLVED (backward). The
    # move-pruning rule only removes redundant duplicates, never a shortest path.
    fwd_seen: dict[str, tuple[str, ...]] = {state: ()}
    bwd_seen: dict[str, tuple[str, ...]] = {SOLVED: ()}
    fwd_frontier = dict(fwd_seen)
    bwd_frontier = dict(bwd_seen)
    fwd_depth = bwd_depth = 0

    while fwd_depth + bwd_depth < max_depth:
        # Grow the smaller frontier; on a tie, alternate starting with forward.
        if len(fwd_frontier) <= len(bwd_frontier):
            fwd_frontier = _expand(fwd_frontier, fwd_seen)
            fwd_depth += 1
            hits = [s for s in fwd_frontier if s in bwd_seen]
        else:
            bwd_frontier = _expand(bwd_frontier, bwd_seen)
            bwd_depth += 1
            hits = [s for s in bwd_frontier if s in fwd_seen]
        if hits:
            best = min(hits, key=lambda s: len(fwd_seen[s]) + len(bwd_seen[s]))
            # bwd path goes SOLVED -> best; invert it to go best -> SOLVED.
            back = [inverse_move(m) for m in reversed(bwd_seen[best])]
            solution = list(fwd_seen[best]) + back
            return OptimalResult(len(solution), solution, True, max_depth)
        if not fwd_frontier or not bwd_frontier:
            break
    return OptimalResult(None, None, False, max_depth)
