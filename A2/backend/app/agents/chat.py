"""Frontier LLM via OpenRouter chat completions (Claude Opus 5.5):
POST {openrouter}/v1/chat/completions

The LLM gets the same observation and move definitions as the decision
models and must answer with exactly ``{"move": "<move>"}``. A JSON schema with
an enum of the 18 moves constrains the output. The reply is still validated
strictly: anything that isn't exactly that object is logged as malformed and
never coerced into a move.
"""

from __future__ import annotations

import json

from ..cube.engine import is_valid_move
from ..gateway import TransportError
from ..prompts import MOVE_JSON_SCHEMA, chat_messages
from .base import Agent, Decision, from_gateway, from_transport_error


def parse_move_reply(content: object) -> tuple[str | None, str | None, str | None]:
    """Return (move, error_kind, error) for a raw assistant message."""
    if not isinstance(content, str) or not content.strip():
        return None, "malformed", "Empty response content"
    try:
        obj = json.loads(content)
    except json.JSONDecodeError as exc:
        return None, "malformed", f"Not valid JSON: {exc.msg}"
    if not isinstance(obj, dict) or set(obj) != {"move"}:
        return None, "malformed", 'Expected exactly {"move": "<move>"}'
    move = obj["move"]
    if not is_valid_move(move):
        return None, "illegal", f"Model chose {move!r}, which is not a legal move"
    return move, None, None


class ChatAgent(Agent):
    """OpenRouter chat completions."""

    path = "/v1/chat/completions"

    def payload(self, observation: dict) -> dict:
        s = self.settings
        payload: dict = {
            "model": self.spec.model_id,
            "messages": chat_messages(observation),
            "max_tokens": s.llm_max_tokens,
        }
        if s.llm_structured_output:
            payload["response_format"] = {"type": "json_schema", "json_schema": MOVE_JSON_SCHEMA}
            # Only route to providers that honour structured outputs.
            payload["provider"] = {"require_parameters": True}
        effort = s.llm_reasoning_effort.strip()
        if effort:
            payload["reasoning"] = {"effort": effort, "exclude": True}
        return payload

    @staticmethod
    def cost(data: dict) -> float | None:
        return (data.get("usage") or {}).get("cost")

    @staticmethod
    def content(data: dict) -> object:
        return data["choices"][0]["message"].get("content")

    async def decide(self, observation: dict) -> Decision:
        try:
            res = await self.gateway.post(self.spec, self.path, self.payload(observation), self.cost)
        except TransportError as exc:
            return from_transport_error(exc)

        data = res.data
        if data.get("error"):
            return from_gateway(res, None, raw=data, error_kind="api_error", error=str(data["error"])[:300])
        try:
            content = self.content(data)
        except (KeyError, IndexError, TypeError):
            return from_gateway(res, None, raw=data, error_kind="malformed", error="Response has no message content")
        move, kind, err = parse_move_reply(content)
        return from_gateway(res, move, raw=content, error_kind=kind, error=err,
                            extra={"served_model": data.get("model"), "usage": data.get("usage")})
