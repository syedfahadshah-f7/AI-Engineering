"""JSON + CSV persistence of benchmark sessions.

Each provider has its own folder (results/mock, results/openrouter), so
simulated runs never mix with the real experiment.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .runner import Session

CSV_FIELDS = [
    "session_id", "provider", "puzzle_id", "test_set", "model_key", "model_name", "model_id", "category",
    "status", "solved", "move_limit", "move_count", "optimal_moves", "optimal_exact", "reference_moves",
    "optimality_gap", "avg_move_latency_s", "avg_live_latency_s", "avg_cache_time_s", "total_time_s",
    "api_calls", "cache_hits", "invalid_count", "api_error_count", "retries", "facelets_correct",
    "cost_usd", "move_sequence",
]


def _dir(results_dir: Path, provider: str) -> Path:
    d = results_dir / provider
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_session(results_dir: Path, session: "Session") -> Path:
    d = _dir(results_dir, session.provider)
    path = d / f"{session.id}.json"
    doc = {**session.summary(), "puzzles": session.puzzles, "trials": session.trials}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    tmp.replace(path)
    with (d / f"{session.id}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for t in session.trials:
            w.writerow({**t, "session_id": session.id, "move_sequence": " ".join(t["move_sequence"])})
    return path


def load_sessions(results_dir: Path, provider: str) -> list[dict]:
    out = []
    for p in sorted(_dir(results_dir, provider).glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out
