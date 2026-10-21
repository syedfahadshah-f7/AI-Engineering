"""End-to-end rehearsal of the real OpenRouter experiment, fully offline.

A fake transport stands in for OpenRouter. The real runner, gateway, cache and
budget ledger run on top of it, in temporary folders, so this checks the
course rules (5 Claude requests, 20 per decision model, 65 total, cache,
persistence across restarts) without any network access or real key.
"""

import json
import logging

import httpx
import pytest

import app.benchmark.runner as runner
from app.benchmark.runner import SessionManager
from app.config import Settings


def _settings(tmp_path):
    return Settings(_env_file=None, provider="openrouter", openrouter_api_key="fake-key",
                    data_dir=tmp_path / "data", results_dir=tmp_path / "results", log_dir=tmp_path / "logs",
                    race_pause_s=0)


@pytest.fixture
def fake_openrouter(monkeypatch):
    """Patch httpx.AsyncClient used by the runner so it talks to a counting fake."""
    received: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        received[body["model"]] = received.get(body["model"], 0) + 1
        assert request.headers["authorization"] == "Bearer fake-key"
        if request.url.path == "/api/alpha/decisions":
            return httpx.Response(200, json={"answers": {"next_move": {"type": "choice", "choice": "U", "confidence": 0.5,
                                                                       "probabilities": {"U": 0.5, "R": 0.5}}},
                                             "usage": {"cost": 0.0002}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"move": "U"}'}}],
                                         "usage": {"cost": 0.05}})

    real = httpx.AsyncClient
    monkeypatch.setattr(runner.httpx, "AsyncClient",
                        lambda *a, **k: real(transport=httpx.MockTransport(handler)))
    return received


async def _run(mgr, seed=1):
    session = mgr.create("three", [seed])
    await session.task
    return session


async def test_real_experiment_respects_every_budget_rule(tmp_path, fake_openrouter):
    s = _settings(tmp_path)
    mgr = SessionManager(s)
    session = await _run(mgr)
    assert session.status == "completed"

    by_key = {t["model_key"]: t for t in session.trials}
    # Claude: at most 5 requests and 5 moves; never solves with a constant "U".
    llm = by_key["llm"]
    assert llm["api_calls"] <= 5 and llm["move_count"] <= 5 and not llm["solved"]
    assert llm["status"] in ("move_limit", "budget_limit")
    for key in ("jev", "luna", "clef"):
        assert by_key[key]["api_calls"] <= 20 and by_key[key]["move_count"] <= 20

    usage = json.loads((s.data_dir / "usage.json").read_text())["providers"]["openrouter"]
    assert usage["total_calls"] <= 65
    assert usage["total_calls"] == sum(fake_openrouter.values())  # ledger == what the fake really received
    assert fake_openrouter["anthropic/claude-opus-5.5"] <= 5
    assert all(fake_openrouter.get(m, 0) <= 20 for m in (s.jev_model, s.luna_model, s.clef_model))
    # Actual cost is tracked from the API's usage.cost, not estimated.
    assert usage["cost_usd"] == pytest.approx(sum(t["cost_usd"] for t in session.trials))

    # One good experiment: a second puzzle in one OpenRouter session is refused.
    with pytest.raises(ValueError, match="limited to 1 puzzle"):
        mgr.create("three", [1, 2])


async def test_rerun_and_restart_reuse_cache_and_keep_counters(tmp_path, fake_openrouter):
    s = _settings(tmp_path)
    s.log_dir.mkdir(parents=True)
    handler = logging.FileHandler(s.log_dir / "api.log", encoding="utf-8")
    api_log = logging.getLogger("api")
    old_level = api_log.level
    api_log.addHandler(handler)
    api_log.setLevel(logging.INFO)
    try:
        first = await _run(SessionManager(s))
        await _rerun_checks(s, first, fake_openrouter)
    finally:
        handler.flush()
        api_log.removeHandler(handler)
        api_log.setLevel(old_level)
        handler.close()


async def _rerun_checks(s, first, fake_openrouter):
    sent_after_first = sum(fake_openrouter.values())
    ledger_after_first = json.loads((s.data_dir / "usage.json").read_text())

    # "Restart the application": brand-new manager over the same data folder.
    mgr2 = SessionManager(s)
    second = await _run(mgr2)

    assert sum(fake_openrouter.values()) == sent_after_first  # not a single new live request
    assert all(t["api_calls"] == 0 for t in second.trials)
    assert sum(t["cache_hits"] for t in second.trials) >= sum(t["move_count"] for t in first.trials)
    assert json.loads((s.data_dir / "usage.json").read_text()) == ledger_after_first  # counters not reset
    assert all(t["cost_usd"] == 0 for t in second.trials)
    # Same decisions as the first run, served from cache, with their original live latency retained.
    assert [t["move_sequence"] for t in first.trials] == [t["move_sequence"] for t in second.trials]
    hit_moves = [m for t in second.trials for m in t["moves"] if m["cached"]]
    assert hit_moves and all(m["cache_time_s"] is not None and m["live_latency_s"] is None for m in hit_moves)
    log = (s.log_dir / "api.log").read_text()
    assert "CACHE HIT" in log and "REQUEST" in log and "live latency" in log
    assert mgr2.budget()["openrouter"]["total_calls"] == ledger_after_first["providers"]["openrouter"]["total_calls"]


async def test_exhausted_ledger_blocks_all_requests(tmp_path, fake_openrouter):
    s = _settings(tmp_path)
    s.data_dir.mkdir(parents=True)
    (s.data_dir / "usage.json").write_text(json.dumps({"providers": {"openrouter": {
        "total_calls": 65, "cost_usd": 0.0, "models": {}}}}))
    session = await _run(SessionManager(s))
    assert sum(fake_openrouter.values()) == 0
    assert all(t["status"] == "budget_limit" and t["move_count"] == 0 for t in session.trials)
