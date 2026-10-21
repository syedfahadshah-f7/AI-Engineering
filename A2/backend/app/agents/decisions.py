"""System-1 decision models (Jev, GPT-6 Luna Decisions, Cloudflare Clef) via the
OpenRouter Decisions API: POST {openrouter}/alpha/decisions

The body is ``state`` plus one typed ``choice`` question whose options are the
18 legal moves. The answer is read from ``answers.next_move.choice`` together
with its ``confidence`` and ``probabilities``.
"""

from __future__ import annotations

from ..cube.engine import is_valid_move
from ..gateway import TransportError
from ..prompts import decision_question
from .base import Agent, Decision, from_gateway, from_transport_error

PATH = "/alpha/decisions"


def _cost(data: dict) -> float | None:
    return (data.get("usage") or {}).get("cost")


class DecisionsAgent(Agent):
    def payload(self, observation: dict) -> dict:
        return {"model": self.spec.model_id, "state": observation, "questions": decision_question()}

    async def decide(self, observation: dict) -> Decision:
        try:
            res = await self.gateway.post(self.spec, PATH, self.payload(observation), _cost)
        except TransportError as exc:
            return from_transport_error(exc)

        data = res.data
        answer = (data.get("answers") or {}).get("next_move")
        if not isinstance(answer, dict) or "choice" not in answer:
            return from_gateway(res, None, raw=data, error_kind="malformed",
                                error="Response has no answers.next_move.choice")
        move = answer.get("choice")
        probs = answer.get("probabilities")
        valid = is_valid_move(move)
        return from_gateway(
            res,
            move if valid else None,
            raw=answer,
            confidence=answer.get("confidence"),
            probabilities=probs if isinstance(probs, dict) else None,
            error_kind=None if valid else "illegal",
            error=None if valid else f"Model chose {move!r}, which is not a legal move",
            extra={"served_model": data.get("model"), "provider": data.get("provider")},
        )
