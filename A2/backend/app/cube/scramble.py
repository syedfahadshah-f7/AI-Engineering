"""Reproducible random scrambles for the three test sets in the assignment."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .engine import FACES, SOLVED, apply_moves
from .solver import solve_optimal

# Scramble length ranges from section 6 of the assignment.
TEST_SETS: dict[str, tuple[int, int]] = {
    # Course instruction for the OpenRouter run: exactly 3 moves from solved.
    "three": (3, 3),
    "warmup": (3, 4),
    "primary": (4, 5),
    "extension": (15, 20),
}

_OPPOSITE = {"U": "D", "D": "U", "R": "L", "L": "R", "F": "B", "B": "F"}


def random_scramble(length: int, rng: random.Random) -> list[str]:
    """WCA-style random turns: never the same face twice in a row, and never
    X Y X where X and Y are opposite faces (that would cancel a turn)."""
    moves: list[str] = []
    while len(moves) < length:
        face = rng.choice(FACES)
        if moves and moves[-1][0] == face:
            continue
        if len(moves) >= 2 and moves[-2][0] == face and _OPPOSITE[face] == moves[-1][0]:
            continue
        moves.append(face + rng.choice(("", "'", "2")))
    return moves


@dataclass
class Puzzle:
    id: str
    test_set: str
    seed: int
    scramble: list[str]
    state: str
    optimal_moves: int | None  # exact distance when known
    optimal_solution: list[str] | None
    optimal_exact: bool
    reference_moves: int = field(init=False)  # what the optimality gap is measured against

    def __post_init__(self) -> None:
        # When BFS cannot prove the optimum (long extension scrambles) we fall back
        # to the scramble length, which is an upper bound on the true distance.
        self.reference_moves = self.optimal_moves if self.optimal_moves is not None else len(self.scramble)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "test_set": self.test_set,
            "seed": self.seed,
            "scramble": self.scramble,
            "state": self.state,
            "optimal_moves": self.optimal_moves,
            "optimal_solution": self.optimal_solution,
            "optimal_exact": self.optimal_exact,
            "reference_moves": self.reference_moves,
        }


def make_puzzle(test_set: str, seed: int, max_optimal_depth: int = 10) -> Puzzle:
    if test_set not in TEST_SETS:
        raise ValueError(f"Unknown test set {test_set!r}; choose from {', '.join(TEST_SETS)}")
    rng = random.Random(f"{test_set}:{seed}")
    lo, hi = TEST_SETS[test_set]
    # The extension states are far beyond the exact-search horizon, so skip
    # the (fruitless) search there and use the scramble length upper bound.
    depth = max_optimal_depth if test_set != "extension" else 0
    while True:
        scramble = random_scramble(rng.randint(lo, hi), rng)
        state = apply_moves(SOLVED, scramble)
        if state == SOLVED:
            continue
        opt = solve_optimal(state, max_depth=depth) if depth else None
        # "three": the state must be *exactly* 3 moves away (BFS-verified),
        # not merely produced by 3 turns.
        if test_set == "three" and (opt is None or opt.distance != 3):
            continue
        break
    return Puzzle(
        id=f"{test_set}-{seed}",
        test_set=test_set,
        seed=seed,
        scramble=scramble,
        state=state,
        optimal_moves=opt.distance if opt else None,
        optimal_solution=opt.solution if opt else None,
        optimal_exact=bool(opt and opt.exact),
    )
