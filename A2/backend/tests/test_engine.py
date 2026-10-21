import random

import pytest

from app.cube.engine import (
    MOVES, SOLVED, InvalidMoveError, apply_move, apply_moves, inverse_sequence, is_solved, validate_state,
)

# Reference states produced by the Kociemba two-phase package's facelet convention.
REFERENCE = {
    "R": "UUFUUFUUFRRRRRRRRRFFDFFDFFDDDBDDBDDBLLLLLLLLLUBBUBBUBB",
    "U": "UUUUUUUUUBBBRRRRRRRRRFFFFFFDDDDDDDDDFFFLLLLLLLLLBBBBBB",
}


@pytest.mark.parametrize("move,expected", REFERENCE.items())
def test_reference_states(move, expected):
    assert apply_move(SOLVED, move) == expected


def test_eighteen_moves():
    assert len(MOVES) == 18 and len(set(MOVES)) == 18


@pytest.mark.parametrize("move", MOVES)
def test_each_move_has_order_dividing_four(move):
    s = SOLVED
    for _ in range(4):
        s = apply_move(s, move)
    assert s == SOLVED
    assert apply_move(SOLVED, move) != SOLVED


def test_double_equals_two_quarters():
    for f in "URFDLB":
        assert apply_move(SOLVED, f + "2") == apply_moves(SOLVED, [f, f])
        assert apply_move(SOLVED, f + "'") == apply_moves(SOLVED, [f, f, f])


def test_sexy_move_has_order_six():
    s = SOLVED
    for i in range(6):
        s = apply_moves(s, "R U R' U'")
        assert (s == SOLVED) == (i == 5)


def test_inverse_sequence_restores_solved():
    rng = random.Random(0)
    for _ in range(50):
        seq = [rng.choice(MOVES) for _ in range(25)]
        scrambled = apply_moves(SOLVED, seq)
        validate_state(scrambled)
        assert apply_moves(scrambled, inverse_sequence(seq)) == SOLVED


def test_is_solved():
    assert is_solved(SOLVED)
    assert not is_solved(apply_move(SOLVED, "F"))


def test_invalid_move_rejected():
    with pytest.raises(InvalidMoveError):
        apply_move(SOLVED, "M")
    with pytest.raises(InvalidMoveError):
        apply_move(SOLVED, "r")
