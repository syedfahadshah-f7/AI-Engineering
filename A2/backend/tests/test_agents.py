import json

import httpx
import pytest

from app.agents.chat import ChatAgent, parse_move_reply
from app.agents.decisions import DecisionsAgent
from app.config import Settings
from app.cube.engine import MOVES, SOLVED
from app.gateway import BudgetLedger, Gateway, ResponseCache
from app.prompts import build_observation


def _settings(tmp_path, **kw):
    return Settings(_env_file=None, openrouter_api_key="sk-test", provider="openrouter",
                    data_dir=tmp_path, log_dir=tmp_path / "logs", **kw)


def _spec(settings, key):
    return next(m for m in settings.models if m.key == key)


def _gateway(s, client, tmp_path):
    return Gateway(s, client, ResponseCache(tmp_path / "cache.json"), BudgetLedger(tmp_path / "usage.json"))


OBS = build_observation(SOLVED, ["R"], 20, 10)
DECISION_REPLY = {
    "id": "gen-dec-1", "model": "typesafe/jev-1.13-x", "provider": "TypeSafe",
    "answers": {"next_move": {"type": "choice", "choice": "R'", "confidence": 0.8,
                              "probabilities": {"R'": 0.9, "U": 0.1}}},
    "usage": {"input_tokens": 10, "output_tokens": 2, "cost": 0.0001},
}


async def test_decisions_agent_parses_choice(tmp_path):
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json=DECISION_REPLY)

    s = _settings(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        d = await DecisionsAgent(_spec(s, "jev"), s, _gateway(s, client, tmp_path)).decide(OBS)
    assert d.move == "R'" and d.confidence == 0.8 and d.cost == 0.0001 and not d.cached
    assert seen["url"] == "https://openrouter.ai/api/alpha/decisions"
    assert seen["auth"] == "Bearer sk-test"
    q = seen["body"]["questions"]["next_move"]
    assert q["type"] == "choice" and list(q["criteria"]) == list(MOVES)
    assert seen["body"]["state"]["cube_facelets"] == SOLVED


async def test_cache_hit_skips_api_and_survives_restart(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=DECISION_REPLY)

    s = _settings(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = await DecisionsAgent(_spec(s, "jev"), s, _gateway(s, client, tmp_path)).decide(OBS)
        # A fresh cache/ledger instance = an application restart.
        second = await DecisionsAgent(_spec(s, "jev"), s, _gateway(s, client, tmp_path)).decide(OBS)
    assert calls["n"] == 1
    assert not first.cached and first.api_calls == 1 and first.live_latency_s is not None
    assert second.cached and second.api_calls == 0 and second.cost == 0
    assert second.cache_time_s is not None and second.live_latency_s is None
    assert second.latency_s == pytest.approx(first.live_latency_s)  # original live latency is kept
    usage = json.loads((tmp_path / "usage.json").read_text())
    assert usage["providers"]["openrouter"]["total_calls"] == 1


async def test_cache_is_per_model(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=DECISION_REPLY)

    s = _settings(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gw = _gateway(s, client, tmp_path)
        await DecisionsAgent(_spec(s, "jev"), s, gw).decide(OBS)
        await DecisionsAgent(_spec(s, "luna"), s, gw).decide(OBS)
    assert calls["n"] == 2


async def test_llm_cap_blocks_sixth_request_even_after_restart(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"move": "F2"}'}}]})

    s = _settings(tmp_path)
    spec = _spec(s, "llm")
    assert spec.call_cap == 5 and spec.move_limit == 5
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        for i in range(5):  # distinct requests, so no cache hits
            obs = build_observation(SOLVED, ["R"] * (i + 1), 5, 10)
            assert (await ChatAgent(spec, s, _gateway(s, client, tmp_path)).decide(obs)).move == "F2"
        blocked = await ChatAgent(spec, s, _gateway(s, client, tmp_path)).decide(build_observation(SOLVED, ["U"], 5, 10))
    assert calls["n"] == 5
    assert blocked.move is None and blocked.error_kind == "budget" and blocked.api_calls == 0


async def test_total_cap_and_failed_requests_count(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503, text="overloaded")

    s = _settings(tmp_path, total_call_cap=3, max_transport_retries=5)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gw = _gateway(s, client, tmp_path)
        gw_sleep_free = gw
        import app.gateway as g

        async def no_sleep(_):
            return None

        orig = g.asyncio.sleep
        g.asyncio.sleep = no_sleep
        try:
            d = await DecisionsAgent(_spec(s, "clef"), s, gw_sleep_free).decide(OBS)
        finally:
            g.asyncio.sleep = orig
    assert calls["n"] == 3  # retries stopped by the overall cap, failures counted
    assert d.move is None and d.error_kind == "budget" and d.api_calls == 3


async def test_errors_are_not_cached(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    s = _settings(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gw = _gateway(s, client, tmp_path)
        d = await DecisionsAgent(_spec(s, "clef"), s, gw).decide(OBS)
    assert d.error_kind == "api_error" and calls["n"] == 1 and len(gw.cache) == 0


async def test_chat_agent_uses_structured_output(tmp_path):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": '{"move": "F2"}'}}],
                                         "usage": {"cost": 0.002}})

    s = _settings(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        d = await ChatAgent(_spec(s, "llm"), s, _gateway(s, client, tmp_path)).decide(OBS)
    assert d.move == "F2" and d.cost == 0.002
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    rf = seen["body"]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["schema"]["properties"]["move"]["enum"] == list(MOVES)
    assert seen["body"]["model"] == "anthropic/claude-opus-5.5"


@pytest.mark.parametrize("content,kind", [
    ('{"move": "R"}', None),
    ('{"move": "X"}', "illegal"),
    ('```json\n{"move": "R"}\n```', "malformed"),
    ('{"move": "R", "why": "x"}', "malformed"),
    ("R", "malformed"),
    ("", "malformed"),
    (None, "malformed"),
])
def test_parse_move_reply_is_strict(content, kind):
    move, k, _ = parse_move_reply(content)
    assert k == kind
    assert (move == "R") == (kind is None)


def test_decision_question_is_identical_for_every_decision_model(tmp_path):
    """Same wording and same 18 options for Jev, Luna and Clef; only the model id differs."""
    s = _settings(tmp_path)
    payloads = [DecisionsAgent(_spec(s, k), s, None).payload(OBS) for k in ("jev", "luna", "clef")]
    assert len({json.dumps({**p, "model": None}, sort_keys=True) for p in payloads}) == 1
    assert [p["model"] for p in payloads] == [s.jev_model, s.luna_model, s.clef_model]
