"""Deterministic 3x3 Rubik's Cube engine.

State representation
--------------------
A cube state is a 54-character facelet string in the standard Kociemba order::

    U1..U9  R1..R9  F1..F9  D1..D9  L1..L9  B1..B9

Each character is the face letter of the centre whose colour the sticker has,
so the solved cube is ``UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB``.
Facelets on each face are numbered row by row as seen when looking straight
at that face (U viewed with B at the top, D viewed with F at the top, the four
side faces viewed with U at the top).

Moves
-----
The 18 face turns of the half-turn metric (HTM): ``X``, ``X'`` and ``X2`` for
X in U, R, F, D, L, B. ``X`` is a 90 degree clockwise turn when looking at
face X, ``X'`` is counter-clockwise and ``X2`` is a half turn. Every move
counts as one move, which is the metric God's number (20) is stated in.

The move permutations are *derived* from a 3D model of the 54 stickers rather
than typed in by hand, so there is no hand-written table that could contain
a typo. The tests check the result against published reference states.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

FACES = "URFDLB"
SOLVED = "".join(face * 9 for face in FACES)

MOVES: tuple[str, ...] = tuple(f + s for f in FACES for s in ("", "'", "2"))

MOVE_DESCRIPTIONS: dict[str, str] = {}
_FACE_NAMES = {
    "U": "upper (top)",
    "R": "right",
    "F": "front",
    "D": "down (bottom)",
    "L": "left",
    "B": "back",
}
for _f in FACES:
    _n = _FACE_NAMES[_f]
    MOVE_DESCRIPTIONS[_f] = f"Turn the {_n} face clockwise by 90 degrees"
    MOVE_DESCRIPTIONS[_f + "'"] = f"Turn the {_n} face counterclockwise by 90 degrees"
    MOVE_DESCRIPTIONS[_f + "2"] = f"Turn the {_n} face by 180 degrees"

Vec = tuple[int, int, int]

# Outward normal of every face. Axes: +x = R, +y = U, +z = F.
FACE_NORMALS: dict[str, Vec] = {
    "U": (0, 1, 0),
    "R": (1, 0, 0),
    "F": (0, 0, 1),
    "D": (0, -1, 0),
    "L": (-1, 0, 0),
    "B": (0, 0, -1),
}


@dataclass(frozen=True)
class Sticker:
    """One facelet: the cubie it sits on and the direction it faces."""

    index: int
    face: str
    position: Vec  # cubie centre, each coordinate in {-1, 0, 1}
    normal: Vec


def _face_grid(face: str) -> list[Vec]:
    """Cubie positions of facelets 1..9 of ``face``, in reading order."""
    out: list[Vec] = []
    for row in range(3):
        for col in range(3):
            a = col - 1  # left -> right
            b = 1 - row  # top -> bottom
            if face == "U":  # viewed from above, B at the top
                out.append((a, 1, -b))
            elif face == "D":  # viewed from below, F at the top
                out.append((a, -1, b))
            elif face == "F":
                out.append((a, b, 1))
            elif face == "B":  # viewed from behind: left of view is +x
                out.append((-a, b, -1))
            elif face == "R":  # viewed from the right: left of view is +z
                out.append((1, b, -a))
            elif face == "L":  # viewed from the left: left of view is -z
                out.append((-1, b, a))
    return out


STICKERS: tuple[Sticker, ...] = tuple(
    Sticker(index=fi * 9 + k, face=face, position=pos, normal=FACE_NORMALS[face])
    for fi, face in enumerate(FACES)
    for k, pos in enumerate(_face_grid(face))
)
_LOOKUP: dict[tuple[Vec, Vec], int] = {(s.position, s.normal): s.index for s in STICKERS}


def _rotate(v: Vec, axis: Vec, quarter_turns: int) -> Vec:
    """Rotate integer vector ``v`` about a unit ``axis`` by +90 deg * quarter_turns
    (right-hand rule, i.e. counter-clockwise when looking down the axis)."""
    x, y, z = v
    for _ in range(quarter_turns % 4):
        if axis[0]:
            s = axis[0]
            y, z = -s * z, s * y
        elif axis[1]:
            s = axis[1]
            z, x = -s * x, s * z
        else:
            s = axis[2]
            x, y = -s * y, s * x
    return (x, y, z)


def _build_permutation(face: str, quarter_turns_clockwise: int) -> tuple[int, ...]:
    """``perm[i] = j`` means the new sticker at index i comes from old index j."""
    axis = FACE_NORMALS[face]
    # Clockwise when looking at the face = negative rotation about its normal.
    q = -quarter_turns_clockwise
    perm = list(range(54))
    for s in STICKERS:
        layer = sum(p * a for p, a in zip(s.position, axis))
        if layer != 1:
            continue
        dest = _LOOKUP[(_rotate(s.position, axis, q), _rotate(s.normal, axis, q))]
        perm[dest] = s.index
    return tuple(perm)


PERMUTATIONS: dict[str, tuple[int, ...]] = {}
for _f in FACES:
    PERMUTATIONS[_f] = _build_permutation(_f, 1)
    PERMUTATIONS[_f + "2"] = _build_permutation(_f, 2)
    PERMUTATIONS[_f + "'"] = _build_permutation(_f, 3)


class InvalidMoveError(ValueError):
    pass


def is_valid_move(move: object) -> bool:
    return isinstance(move, str) and move in PERMUTATIONS


def apply_move(state: str, move: str) -> str:
    """Return the state reached by applying one move to ``state``."""
    perm = PERMUTATIONS.get(move)
    if perm is None:
        raise InvalidMoveError(f"Unknown move {move!r}; allowed: {', '.join(MOVES)}")
    return "".join(state[j] for j in perm)


def parse_moves(sequence: str | Iterable[str]) -> list[str]:
    moves = sequence.split() if isinstance(sequence, str) else list(sequence)
    for m in moves:
        if not is_valid_move(m):
            raise InvalidMoveError(f"Unknown move {m!r}")
    return moves


def apply_moves(state: str, sequence: str | Iterable[str]) -> str:
    for m in parse_moves(sequence):
        state = apply_move(state, m)
    return state


def inverse_move(move: str) -> str:
    if move.endswith("2"):
        return move
    if move.endswith("'"):
        return move[0]
    return move + "'"


def inverse_sequence(sequence: str | Iterable[str]) -> list[str]:
    return [inverse_move(m) for m in reversed(parse_moves(sequence))]


def is_solved(state: str) -> bool:
    """True when every face shows a single colour (matching its centre)."""
    return all(len(set(state[i * 9 : i * 9 + 9])) == 1 for i in range(6))


def validate_state(state: str) -> None:
    if len(state) != 54 or any(c not in FACES for c in state):
        raise ValueError("State must be 54 characters drawn from URFDLB")
    for f in FACES:
        if state.count(f) != 9:
            raise ValueError(f"State must contain exactly nine {f} facelets")


def face_grids(state: str) -> dict[str, list[str]]:
    """Human-readable 3x3 rows per face, e.g. {"U": ["UUU", "UUU", "UUF"], ...}."""
    return {
        f: [state[i * 9 + r * 3 : i * 9 + r * 3 + 3] for r in range(3)]
        for i, f in enumerate(FACES)
    }


def sticker_geometry() -> list[dict]:
    """3D layout of the 54 facelets, shared with the frontend renderer so both
    sides agree on what each index of the state string means."""
    return [
        {"index": s.index, "face": s.face, "position": list(s.position), "normal": list(s.normal)}
        for s in STICKERS
    ]
