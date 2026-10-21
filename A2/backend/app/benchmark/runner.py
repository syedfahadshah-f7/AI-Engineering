"""Runs races: every model plays the same puzzle, move by move.

A *session* is a list of puzzles (one race each). Every model gets identical
rules: the same start state, observation format, move instructions, timeouts
and retry policy. Progress is published as events that the API streams to the
browser over Server-Sent Events.

Every loop here is bounded: a trial ends when the cube is solved, the model's
move limit is reached, the time limit passes, the budget refuses a request, or
the model keeps returning unusable output. There is no open-ended loop that
could keep calling an API.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from ..agents.base import Agent
from ..agents.registry import build_agent
from ..config import ModelSpec, Settings
from ..cube.engine import apply_move, is_solved
from ..cube.scramble import Puzzle, make_puzzle
from ..gateway import BudgetLedger, Gateway, ResponseCache, log
from ..prompts import build_observation
from . import store


def _facelets_correct(state: str) -> int:
    return sum(state[i] == state[(i // 9) * 9 + 4] for i in range(54))


def _truncate(value: Any, limit: int = 400) -> Any:
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= limit else text[:limit] + "..."


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


async def run_trial(agent: Agent, puzzle: Puzzle, settings: Settings, emit) -> dict:
    spec = agent.spec
    move_limit = spec.move_limit
    state = puzzle.state
    history: list[str] = []
    moves: list[dict] = []
    invalid: list[dict] = []
    model_latencies: list[float] = []  # one per model answer (live, or original latency if cached)
    live_latencies: list[float] = []  # live API requests only
    cache_times: list[float] = []  # cache hits only
    api_calls = 0
    cache_hits = 0
    api_errors = 0
    cost = 0.0
    status = "running"
    error: str | None = None
    limit = settings.trial_time_limit_s
    start = time.perf_counter()

    def elapsed() -> float:
        return time.perf_counter() - start

    while True:
        if is_solved(state):
            status = "solved"
            break
        if len(history) >= move_limit:
            status = "move_limit"
            break
        if limit and elapsed() >= limit:
            status = "time_limit"
            break

        emit({"type": "thinking", "model": spec.key, "move_index": len(history) + 1, "elapsed_s": elapsed()})
        obs = build_observation(state, history, move_limit, settings.recent_moves_window)

        decision = None
        for ask in range(settings.max_invalid_retries + 1):
            try:
                remaining = (limit - elapsed()) if limit else None
                decision = await asyncio.wait_for(agent.decide(obs), timeout=remaining)
            except asyncio.TimeoutError:
                decision = None
                status = "time_limit"
                break
            api_calls += decision.api_calls
            cost += decision.cost or 0.0
            if decision.cached:
                cache_hits += 1
                if decision.cache_time_s is not None:
                    cache_times.append(decision.cache_time_s)
            elif decision.live_latency_s is not None:
                live_latencies.append(decision.live_latency_s)
            if decision.error_kind != "budget":
                model_latencies.append(decision.latency_s)
            if decision.move is not None:
                break
            if decision.error_kind == "api_error":
                api_errors += 1
            entry = {
                "move_index": len(history) + 1,
                "ask": ask + 1,
                "kind": decision.error_kind,
                "error": decision.error,
                "raw": _truncate(decision.raw),
                "latency_s": decision.latency_s,
                "cached": decision.cached,
            }
            invalid.append(entry)
            emit({"type": "invalid", "model": spec.key, **entry, "elapsed_s": elapsed()})
            log.warning(f"UNUSABLE   | {spec.provider} | {spec.model_id} | move {entry['move_index']} | "
                        f"{entry['kind']}: {entry['error']}")
            decision = None
            if entry["kind"] in ("api_error", "budget"):
                break  # don't re-ask after transport failures or when the budget refuses
        if status == "time_limit":
            break
        if decision is None:
            last = invalid[-1] if invalid else {}
            kind = last.get("kind")
            status = {"api_error": "api_error", "budget": "budget_limit"}.get(kind, "invalid_output")
            error = last.get("error")
            break

        state = apply_move(state, decision.move)
        history.append(decision.move)
        probs = decision.probabilities or {}
        top = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:3]
        record = {
            "index": len(history),
            "move": decision.move,
            "latency_s": decision.latency_s,
            "live_latency_s": decision.live_latency_s,
            "cache_time_s": decision.cache_time_s,
            "cached": decision.cached,
            "api_calls": decision.api_calls,
            "confidence": decision.confidence,
            "top_probabilities": dict(top),
            "cost_usd": decision.cost or 0.0,
            "elapsed_s": elapsed(),
            "state": state,
        }
        moves.append(record)
        emit({"type": "move", "model": spec.key, **record})

    total = elapsed()
    solved = status == "solved"
    gap = (len(history) - puzzle.reference_moves) if solved else None
    result = {
        "model_key": spec.key,
        "model_id": spec.model_id,
        "model_name": spec.name,
        "category": spec.category,
        "provider": spec.provider,
        "puzzle_id": puzzle.id,
        "test_set": puzzle.test_set,
        "status": status,
        "solved": solved,
        "error": error,
        "move_limit": move_limit,
        "move_count": len(history),
        "moves": moves,
        "move_sequence": history,
        "invalid_outputs": invalid,
        "invalid_count": sum(1 for i in invalid if i["kind"] in ("malformed", "illegal")),
        "api_error_count": api_errors,
        "api_calls": api_calls,
        "cache_hits": cache_hits,
        # Extra HTTP attempts beyond one per live answer (transport retries).
        "retries": max(0, api_calls - len(live_latencies)),
        "call_count": len(model_latencies),
        "call_latencies": model_latencies,
        "live_latencies": live_latencies,
        "cache_times": cache_times,
        "avg_move_latency_s": _mean(model_latencies),
        "avg_live_latency_s": _mean(live_latencies),
        "avg_cache_time_s": _mean(cache_times),
        "total_time_s": total,
        "optimal_moves": puzzle.optimal_moves,
        "optimal_exact": puzzle.optimal_exact,
        "reference_moves": puzzle.reference_moves,
        "optimality_gap": gap,
        "final_state": state,
        "facelets_correct": _facelets_correct(state),
        "cost_usd": cost,
    }
    log.info(f"TRIAL END  | {spec.provider} | {spec.model_id} | {puzzle.id} | {status} | moves {len(history)} | "
             f"api calls {api_calls} | cache hits {cache_hits} | cost ${cost:.6f} | {total:.2f} s")
    emit({"type": "finished", "model": spec.key, "result": {k: v for k, v in result.items() if k != "moves"}})
    return result


def rank_trials(trials: list[dict]) -> list[str]:
    """Solved first (fewest moves, then fastest); then unsolved by how close
    they got (most facelets correct), then by time."""
    def key(t: dict):
        if t["solved"]:
            return (0, t["move_count"], t["total_time_s"])
        return (1, -t["facelets_correct"], t["total_time_s"])
    return [t["model_key"] for t in sorted(trials, key=key)]


@dataclass
class Session:
    id: str
    test_set: str
    seeds: list[int]
    provider: str
    models: list[ModelSpec]
    created_at: str
    status: str = "pending"
    events: list[dict] = field(default_factory=list)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    puzzles: list[dict] = field(default_factory=list)
    trials: list[dict] = field(default_factory=list)
    task: asyncio.Task | None = None

    @property
    def mock(self) -> bool:
        return self.provider == "mock"

    def emit(self, event: dict) -> None:
        event = {"seq": len(self.events), "t": time.time(), **event}
        self.events.append(event)
        for q in list(self.subscribers):
            q.put_nowait(event)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "test_set": self.test_set,
            "seeds": self.seeds,
            "provider": self.provider,
            "mock": self.mock,
            "status": self.status,
            "created_at": self.created_at,
            "models": [m.model_dump() for m in self.models],
            "puzzle_count": len(self.seeds),
        }


class SessionManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sessions: dict[str, Session] = {}
        self.active: Session | None = None
        self.cache = ResponseCache(settings.data_dir / "cache.json")
        self.ledger = BudgetLedger(settings.data_dir / "usage.json")

    def budget(self) -> dict:
        s = self.settings
        snap = self.ledger.snapshot("openrouter")
        caps = {}
        for spec in s.models if s.active_provider == "openrouter" else []:
            caps[spec.model_id] = spec.call_cap
        return {
            "provider": s.active_provider,
            "capped": s.active_provider == "openrouter",
            "total_cap": s.total_call_cap,
            "openrouter": snap,
            "caps": caps,
            "cache": self.cache.stats(),
        }

    def create(self, test_set: str, seeds: list[int]) -> Session:
        if self.active and self.active.status == "running":
            raise RuntimeError("A benchmark is already running")
        s = self.settings
        if s.active_provider == "openrouter":
            if not s.openrouter_api_key.strip():
                raise ValueError("OPENROUTER_API_KEY is not set in backend/.env")
            if len(seeds) > s.openrouter_max_puzzles:
                raise ValueError(f"OpenRouter runs are limited to {s.openrouter_max_puzzles} puzzle(s) per session "
                                 "(one good experiment).")
        stamp = datetime.now(timezone.utc)
        session = Session(
            id=stamp.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6],
            test_set=test_set,
            seeds=seeds,
            provider=s.active_provider,
            models=s.models,
            created_at=stamp.isoformat(),
        )
        self.sessions[session.id] = session
        self.active = session
        session.status = "running"
        session.task = asyncio.create_task(self._run(session))
        return session

    def cancel(self, session_id: str) -> bool:
        s = self.sessions.get(session_id)
        if not s or not s.task or s.task.done():
            return False
        s.task.cancel()
        return True

    async def _run(self, session: Session) -> None:
        s = self.settings
        session.emit({"type": "session_started", "session": session.summary(), "rules": {
            "max_moves": s.max_moves, "recent_moves_window": s.recent_moves_window,
            "request_timeout_s": s.request_timeout_s, "max_transport_retries": s.max_transport_retries,
            "max_invalid_retries": s.max_invalid_retries, "trial_time_limit_s": s.trial_time_limit_s,
            "metric": "HTM (half-turn metric)",
        }})
        log.info(f"SESSION    | {session.id} | provider {session.provider} | {session.test_set} | seeds {session.seeds}")
        try:
            async with httpx.AsyncClient() as client:
                gateway = Gateway(s, client, self.cache, self.ledger)
                for i, seed in enumerate(session.seeds):
                    puzzle = await asyncio.to_thread(make_puzzle, session.test_set, seed)
                    session.puzzles.append(puzzle.to_dict())
                    session.emit({"type": "race_started", "index": i, "total": len(session.seeds),
                                  "puzzle": puzzle.to_dict()})
                    agents = [build_agent(spec, s, gateway) for spec in session.models]
                    trials = list(await asyncio.gather(*(run_trial(a, puzzle, s, session.emit) for a in agents)))
                    session.trials.extend(trials)
                    session.emit({"type": "race_finished", "index": i, "puzzle_id": puzzle.id,
                                  "ranking": rank_trials(trials), "budget": self.budget()})
                    store.save_session(s.results_dir, session)
                    await asyncio.to_thread(self.cache.flush)
                    if i < len(session.seeds) - 1 and s.race_pause_s > 0:
                        await asyncio.sleep(s.race_pause_s)
            session.status = "completed"
        except asyncio.CancelledError:
            session.status = "cancelled"
        except Exception as exc:  # surface unexpected failures to the UI
            session.status = "failed"
            log.exception("Session failed")
            session.emit({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            if session.trials:
                store.save_session(s.results_dir, session)
            self.cache.flush()
            session.emit({"type": "session_finished", "status": session.status})
