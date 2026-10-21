"""Common agent interface: given an observation, return one move decision."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..config import ModelSpec, Settings
from ..gateway import Gateway, GatewayResult, TransportError


@dataclass
class Decision:
    """Outcome of asking a model for one move.

    ``move`` is None whenever the model's output could not be used. In that case
    ``error_kind`` says why: ``malformed`` (unparseable output), ``illegal``
    (parsed but not one of the 18 moves), ``api_error`` (transport failure) or
    ``budget`` (the request was refused because a call cap was reached).
    """

    move: str | None
    latency_s: float  # model latency: live latency, or the original live latency of a cached response
    api_calls: int = 1  # live HTTP requests actually sent (0 for a cache hit)
    cached: bool = False
    live_latency_s: float | None = None
    cache_time_s: float | None = None
    raw: Any = None
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    cost: float | None = None
    error_kind: str | None = None
    error: str | None = None
    extra: dict = field(default_factory=dict)


def from_gateway(res: GatewayResult, move: str | None, **kw) -> Decision:
    return Decision(
        move,
        res.model_latency_s,
        api_calls=res.api_calls,
        cached=res.cached,
        live_latency_s=res.live_latency_s,
        cache_time_s=res.cache_time_s,
        cost=res.cost_usd,
        **kw,
    )


def from_transport_error(exc: TransportError) -> Decision:
    return Decision(None, exc.latency_s, api_calls=exc.api_calls,
                    live_latency_s=exc.latency_s if exc.api_calls else None,
                    error_kind=exc.kind, error=str(exc))


class Agent(ABC):
    def __init__(self, spec: ModelSpec, settings: Settings, gateway: Gateway | None):
        self.spec = spec
        self.settings = settings
        self.gateway = gateway

    @abstractmethod
    async def decide(self, observation: dict) -> Decision: ...
