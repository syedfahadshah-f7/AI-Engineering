"""The single game-action contract shared by every model.

Both interfaces (Decisions API and chat completions) receive the *same*
observation object and the *same* instructions and move definitions; only the
transport differs.
"""

from __future__ import annotations

import json

from .cube.engine import MOVE_DESCRIPTIONS, MOVES, SOLVED, face_grids

INSTRUCTIONS = (
    "You are solving a standard 3x3 Rubik's Cube. Choose the single next move most likely to "
    "progress toward the solved cube (every face a single colour) using as few total moves as "
    "possible. Moves use the half-turn metric: every listed move counts as one move."
)

FACELET_FORMAT = (
    "cube_facelets is 54 characters in Kociemba order U1-U9, R1-R9, F1-F9, D1-D9, L1-L9, B1-B9. "
    "Each character is the face whose centre has that sticker's colour, so the solved cube is "
    f"{SOLVED}. Facelets of a face are read row by row while looking straight at it: U with B at "
    "the top, D with F at the top, and R, F, L, B with U at the top."
)

COLOURS = {"U": "white", "R": "red", "F": "green", "D": "yellow", "L": "orange", "B": "blue"}


def build_observation(state: str, history: list[str], max_moves: int, window: int) -> dict:
    """The state object every model receives each turn."""
    return {
        "cube_facelets": state,
        "faces": face_grids(state),
        "facelet_format": FACELET_FORMAT,
        "face_colours": COLOURS,
        "recent_moves": history[-window:] if window > 0 else [],
        "moves_made": len(history),
        "moves_remaining": max_moves - len(history),
    }


# Wording of the decision question. GPT-6 Luna Decisions refused a longer
# instruction in testing, so all three decision models use this shorter one,
# which keeps their wording identical (course requirement).
DECISION_INSTRUCTIONS = (
    "Which single move should be applied next to get closer to the solved cube state? Choose exactly one option."
)


def decision_question() -> dict:
    """Typed `choice` question for the Decisions API; the options are the 18 moves."""
    return {
        "next_move": {
            "type": "choice",
            "instructions": DECISION_INSTRUCTIONS,
            "criteria": {m: MOVE_DESCRIPTIONS[m] for m in MOVES},
        }
    }


SYSTEM_PROMPT = (
    f"{INSTRUCTIONS}\n\n"
    "You will receive the current cube state as JSON. "
    f"{FACELET_FORMAT}\n\n"
    "Allowed moves:\n"
    + "\n".join(f"- {m}: {MOVE_DESCRIPTIONS[m]}" for m in MOVES)
    + '\n\nRespond with exactly one JSON object of the form {"move": "<move>"} where <move> is one '
    "of the allowed moves. Do not include any other text."
)


def chat_messages(observation: dict) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Current state:\n" + json.dumps(observation, indent=1)},
    ]


MOVE_JSON_SCHEMA = {
    "name": "next_move",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"move": {"type": "string", "enum": list(MOVES)}},
        "required": ["move"],
        "additionalProperties": False,
    },
}
