from __future__ import annotations

from ..config import ModelSpec, Settings
from ..gateway import Gateway
from .base import Agent
from .chat import ChatAgent
from .decisions import DecisionsAgent
from .mock import MockAgent


def build_agent(spec: ModelSpec, settings: Settings, gateway: Gateway | None) -> Agent:
    if spec.provider == "mock":
        return MockAgent(spec, settings, gateway)
    if spec.interface == "decisions":
        return DecisionsAgent(spec, settings, gateway)
    return ChatAgent(spec, settings, gateway)
