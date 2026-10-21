"""FastAPI entry point: REST + Server-Sent Events API and the built frontend."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from .benchmark import stats, store
from .benchmark.runner import SessionManager
from .config import BACKEND_DIR, PROVIDERS, get_settings
from .cube.engine import MOVE_DESCRIPTIONS, MOVES, SOLVED, sticker_geometry
from .cube.scramble import TEST_SETS, make_puzzle
from .gateway import setup_logging

settings = get_settings()
setup_logging(settings.log_dir)
app = FastAPI(title="Rubik's Cube Race", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
manager = SessionManager(settings)


class SessionRequest(BaseModel):
    test_set: str = "three"
    count: int = Field(1, ge=1, le=50)
    start_seed: int = Field(1, ge=0)
    seeds: list[int] | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.test_set not in TEST_SETS:
            raise ValueError(f"test_set must be one of {list(TEST_SETS)}")
        return self

    def resolved_seeds(self) -> list[int]:
        return self.seeds or list(range(self.start_seed, self.start_seed + self.count))


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/config")
def config():
    s = settings
    return {
        "student_name": s.student_name,
        "roll_number": s.roll_number,
        "provider": s.active_provider,
        "mock": s.is_mock,
        "openrouter_max_puzzles": s.openrouter_max_puzzles,
        "models": [m.model_dump() for m in s.models],
        "test_sets": {k: {"min": lo, "max": hi} for k, (lo, hi) in TEST_SETS.items()},
        "rules": {
            "max_moves": s.max_moves,
            "recent_moves_window": s.recent_moves_window,
            "request_timeout_s": s.request_timeout_s,
            "max_transport_retries": s.max_transport_retries,
            "max_invalid_retries": s.max_invalid_retries,
            "trial_time_limit_s": s.trial_time_limit_s,
            "llm_reasoning_effort": s.llm_reasoning_effort,
            "total_call_cap": s.total_call_cap if s.active_provider == "openrouter" else None,
            "cache_enabled": s.cache_enabled,
            "metric": "HTM",
        },
        "moves": [{"move": m, "description": MOVE_DESCRIPTIONS[m]} for m in MOVES],
        "solved_state": SOLVED,
    }


@app.get("/api/cube/geometry")
def geometry():
    return {"solved_state": SOLVED, "stickers": sticker_geometry()}


@app.get("/api/puzzles/preview")
async def preview(test_set: str = "primary", seed: int = 1):
    if test_set not in TEST_SETS:
        raise HTTPException(400, f"test_set must be one of {list(TEST_SETS)}")
    puzzle = await asyncio.to_thread(make_puzzle, test_set, seed)
    return puzzle.to_dict()


@app.post("/api/sessions")
async def create_session(req: SessionRequest):
    try:
        session = manager.create(req.test_set, req.resolved_seeds())
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return session.summary()


@app.get("/api/budget")
def budget():
    """Live API usage (persistent): requests per model, caps, cost, cache size."""
    return manager.budget()


@app.get("/api/sessions")
def list_sessions():
    live = {sid: s.summary() for sid, s in manager.sessions.items()}
    stored = []
    for provider in PROVIDERS:
        for doc in store.load_sessions(settings.results_dir, provider):
            if doc["id"] not in live:
                doc.pop("trials", None)
                stored.append(doc)
    return {"active": manager.active.summary() if manager.active else None,
            "sessions": list(live.values()) + stored}


@app.post("/api/sessions/{session_id}/cancel")
def cancel_session(session_id: str):
    if not manager.cancel(session_id):
        raise HTTPException(404, "No running session with that id")
    return {"cancelled": session_id}


@app.get("/api/sessions/{session_id}/events")
async def session_events(session_id: str, request: Request):
    session = manager.sessions.get(session_id)
    if session is None:
        raise HTTPException(404, "Unknown or finished session (events are kept in memory only)")

    async def stream():
        queue: asyncio.Queue = asyncio.Queue()
        backlog = list(session.events)
        session.subscribers.add(queue)
        try:
            for ev in backlog:
                yield f"data: {json.dumps(ev)}\n\n"
            last_seq = backlog[-1]["seq"] if backlog else -1
            done = any(ev["type"] == "session_finished" for ev in backlog)
            while not done:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if ev["seq"] <= last_seq:
                    continue
                last_seq = ev["seq"]
                yield f"data: {json.dumps(ev)}\n\n"
                done = ev["type"] == "session_finished"
        finally:
            session.subscribers.discard(queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/stats")
def get_stats(
    test_set: str | None = Query("three"),
    provider: str | None = None,
    sessions: str | None = None,
):
    use = provider or settings.active_provider
    if use not in PROVIDERS:
        raise HTTPException(400, f"provider must be one of {list(PROVIDERS)}")
    docs = store.load_sessions(settings.results_dir, use)
    ids = [s for s in sessions.split(",") if s] if sessions else None
    result = stats.aggregate(docs, test_set=test_set or None, session_ids=ids)
    result["provider"] = use
    result["mock"] = use == "mock"
    return result


@app.get("/api/sessions/{session_id}/trials")
def session_trials(session_id: str):
    for provider in PROVIDERS:
        for doc in store.load_sessions(settings.results_dir, provider):
            if doc["id"] == session_id:
                return doc
    raise HTTPException(404, "Session not found")


# Serve the production frontend build (frontend/dist) when it exists.
DIST = BACKEND_DIR.parent / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = (DIST / path).resolve()
        if path and candidate.is_file() and DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
