"""Offline stand-ins used when no API key is configured (MOCK MODE).

They exist only to exercise the UI and pipeline without spending credits.
The UI shows a MOCK MODE banner and mock results are stored separately, so
they can never be mistaken for real benchmark data.
"""

from __future__ import annotations

import asyncio
import random
import time

from ..cube.engine import MOVES
from ..cube.solver import solve_optimal
from .base import Agent, Decision

# (latency range in seconds, probability of playing an optimal move)
_PROFILES = {
    "llm": ((2.0, 5.0), 0.92),
    "jev": ((0.15, 0.45), 0.45),
    "luna": ((0.25, 0.6), 0.35),
    "clef": ((0.1, 0.3), 0.2),
}


class MockAgent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rng = random.Random()

    async def decide(self, observation: dict) -> Decision:
        (lo, hi), skill = _PROFILES.get(self.spec.key, ((0.2, 0.5), 0.3))
        t0 = time.perf_counter()
        await asyncio.sleep(self.rng.uniform(lo, hi))
        state = observation["cube_facelets"]
        move = self.rng.choice(MOVES)
        if self.rng.random() < skill:
            opt = await asyncio.to_thread(solve_optimal, state, 8)
            if opt.solution:
                move = opt.solution[0]
        conf = round(self.rng.uniform(0.3, 0.95), 3)
        latency = time.perf_counter() - t0
        return Decision(
            move, latency, api_calls=1, live_latency_s=latency, cost=0.0, raw={"mock": True},
            confidence=conf if self.spec.category == "decision" else None,
        )
