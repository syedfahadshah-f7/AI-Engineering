import pytest

from app.agents.base import Agent, Decision
from app.benchmark.runner import rank_trials, run_trial
from app.benchmark.stats import aggregate
from app.config import Settings
from app.cube.scramble import make_puzzle


class ScriptedAgent(Agent):
    """Plays a fixed list of replies (a move string, or a Decision for errors)."""

    def __init__(self, spec, settings, replies):
        super().__init__(spec, settings, None)
        self.replies = list(replies)

    async def decide(self, observation):
        r = self.replies.pop(0) if self.replies else "U"
        return r if isinstance(r, Decision) else Decision(r, 0.01, live_latency_s=0.01)


def _setup(**kw):
    s = Settings(_env_file=None, provider="mock", **kw)
    return s, s.models[1]


async def test_optimal_solve_has_zero_gap():
    s, spec = _setup()
    p = make_puzzle("primary", 1)
    events = []
    t = await run_trial(ScriptedAgent(spec, s, p.optimal_solution), p, s, events.append)
    assert t["status"] == "solved" and t["optimality_gap"] == 0
    assert t["move_count"] == p.optimal_moves
    assert [e["type"] for e in events].count("move") == p.optimal_moves
    assert events[-1]["type"] == "finished"


async def test_move_limit_is_unsuccessful():
    s, spec = _setup(max_moves=4)
    assert spec.move_limit == 4
    p = make_puzzle("primary", 2)
    t = await run_trial(ScriptedAgent(spec, s, ["U", "U", "U", "U'"] * 3), p, s, lambda e: None)
    assert t["status"] == "move_limit" and not t["solved"] and t["move_count"] == 4
    assert t["optimality_gap"] is None


async def test_invalid_outputs_are_counted_and_retried():
    s, spec = _setup(max_invalid_retries=2)
    p = make_puzzle("warmup", 1)
    bad = Decision(None, 0.01, error_kind="malformed", error="nope", raw="hello")
    t = await run_trial(ScriptedAgent(spec, s, [bad, *p.optimal_solution]), p, s, lambda e: None)
    assert t["solved"] and t["invalid_count"] == 1 and t["call_count"] == p.optimal_moves + 1


async def test_too_many_invalid_outputs_end_trial():
    s, spec = _setup(max_invalid_retries=1)
    p = make_puzzle("warmup", 1)
    bad = Decision(None, 0.01, error_kind="illegal", error="X")
    t = await run_trial(ScriptedAgent(spec, s, [bad, bad, bad]), p, s, lambda e: None)
    assert t["status"] == "invalid_output" and t["invalid_count"] == 2 and t["move_count"] == 0


async def test_ranking_and_stats():
    s, _ = _setup()
    p = make_puzzle("primary", 3)
    trials = []
    for i, spec in enumerate(s.models):
        moves = p.optimal_solution if i == 0 else ["U"] * 20
        trials.append(await run_trial(ScriptedAgent(spec, s, moves), p, s, lambda e: None))
    assert rank_trials(trials)[0] == "llm"
    agg = aggregate([{"id": "x", "puzzles": [p.to_dict()], "trials": trials}], test_set="primary")
    llm = agg["models"][0]
    assert llm["success_rate"] == 100 and llm["avg_optimality_gap"] == 0
    assert all(m["success_rate"] == 0 for m in agg["models"][1:])
    assert len(agg["answers"]) == 5


async def test_stats_never_mix_different_llms():
    s, _ = _setup()
    p = make_puzzle("primary", 4)
    spec = s.models[0]
    a = await run_trial(ScriptedAgent(spec, s, p.optimal_solution), p, s, lambda e: None)
    b = {**a, "model_id": "anthropic/claude-sonnet-5.5", "model_name": "Claude Sonnet 5.5"}
    agg = aggregate([{"id": "x", "puzzles": [], "trials": [a, b]}], test_set="primary")
    assert sorted(m["model_id"] for m in agg["models"]) == sorted([a["model_id"], b["model_id"]])


def test_default_move_limit_is_20():
    o = Settings(_env_file=None, provider="openrouter")
    assert o.max_moves == 20
    limits = {m.key: (m.move_limit, m.call_cap) for m in o.models}
    assert limits == {"llm": (5, 5), "jev": (20, 20), "luna": (20, 20), "clef": (20, 20)}


async def test_budget_refusal_ends_trial_unsolved():
    s, spec = _setup()
    p = make_puzzle("three", 1)
    refused = Decision(None, 0.0, api_calls=0, error_kind="budget", error="cap reached")
    t = await run_trial(ScriptedAgent(spec, s, [p.optimal_solution[0], refused]), p, s, lambda e: None)
    assert t["status"] == "budget_limit" and not t["solved"] and t["move_count"] == 1


async def test_cache_hits_and_calls_recorded():
    s, spec = _setup()
    p = make_puzzle("three", 2)
    sol = p.optimal_solution
    replies = [Decision(sol[0], 0.5, api_calls=1, live_latency_s=0.5, cost=0.01),
               Decision(sol[1], 0.7, api_calls=0, cached=True, cache_time_s=0.001),
               Decision(sol[2], 0.4, api_calls=1, live_latency_s=0.4, cost=0.02)]
    t = await run_trial(ScriptedAgent(spec, s, replies), p, s, lambda e: None)
    assert t["solved"] and t["api_calls"] == 2 and t["cache_hits"] == 1
    assert t["live_latencies"] == [0.5, 0.4] and t["cache_times"] == [0.001]
    assert t["cost_usd"] == pytest.approx(0.03) and t["optimality_gap"] == 0
