"""Aggregate trial results into the per-model benchmark statistics.

Metrics (section 3C / section 7 of the assignment):
  * avg_move_latency_s: mean model response time per move (live latency, or the
                        original live latency when the answer was served from cache)
  * avg_live_latency_s / avg_cache_time_s: live API latency and cache lookup time, kept separate
  * avg_total_time_s:   mean wall-clock time per trial, until solved or a limit was reached
  * total_moves / avg_moves: moves executed
  * success_rate:       solved trials / trials, as a percentage
  * avg_optimality_gap: mean of (model moves - exact shortest moves) over solved trials
"""

from __future__ import annotations

from statistics import mean, median


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def model_stats(trials: list[dict]) -> dict:
    latencies = [x for t in trials for x in t.get("call_latencies", [])]
    live = [x for t in trials for x in t.get("live_latencies", [])]
    cached = [x for t in trials for x in t.get("cache_times", [])]
    solved = [t for t in trials if t["solved"]]
    exact_gaps = [t["optimality_gap"] for t in solved if t.get("optimal_exact") and t["optimality_gap"] is not None]
    any_gaps = [t["optimality_gap"] for t in solved if t["optimality_gap"] is not None]
    statuses: dict[str, int] = {}
    for t in trials:
        statuses[t["status"]] = statuses.get(t["status"], 0) + 1
    first = trials[0]
    return {
        "model_key": first["model_key"],
        "provider": first.get("provider"),
        "model_name": first["model_name"],
        "model_id": first["model_id"],
        "category": first["category"],
        "trials": len(trials),
        "solved": len(solved),
        "success_rate": 100.0 * len(solved) / len(trials),
        "avg_move_latency_s": mean(latencies) if latencies else None,
        "median_move_latency_s": median(latencies) if latencies else None,
        "p95_move_latency_s": _pct(latencies, 0.95),
        "avg_total_time_s": mean(t["total_time_s"] for t in trials),
        "total_time_s": sum(t["total_time_s"] for t in trials),
        "avg_solve_time_s": mean(t["total_time_s"] for t in solved) if solved else None,
        "total_moves": sum(t["move_count"] for t in trials),
        "avg_moves": mean(t["move_count"] for t in trials),
        "avg_moves_solved": mean(t["move_count"] for t in solved) if solved else None,
        "avg_optimality_gap": mean(exact_gaps) if exact_gaps else (mean(any_gaps) if any_gaps else None),
        "gap_is_exact": bool(exact_gaps),
        "optimal_solves": sum(1 for g in exact_gaps if g == 0),
        "invalid_outputs": sum(t.get("invalid_count", 0) for t in trials),
        "api_errors": sum(t.get("api_error_count", 0) for t in trials),
        "retries": sum(t.get("retries", 0) for t in trials),
        "calls": len(latencies),
        "api_calls": sum(t.get("api_calls", 0) for t in trials),
        "cache_hits": sum(t.get("cache_hits", 0) for t in trials),
        "avg_live_latency_s": mean(live) if live else None,
        "avg_cache_time_s": mean(cached) if cached else None,
        "cost_usd": sum(t.get("cost_usd") or 0 for t in trials),
        "statuses": statuses,
    }


def aggregate(sessions: list[dict], test_set: str | None = None, session_ids: list[str] | None = None) -> dict:
    trials: list[dict] = []
    puzzles: dict[str, dict] = {}
    used_sessions = []
    for s in sessions:
        if session_ids and s["id"] not in session_ids:
            continue
        sel = [t for t in s.get("trials", []) if not test_set or t["test_set"] == test_set]
        if not sel:
            continue
        used_sessions.append(s["id"])
        trials.extend(sel)
        for p in s.get("puzzles", []):
            puzzles[p["id"]] = p

    # Group by the exact model id so runs with different LLMs in the "llm"
    # slot (e.g. a cheap dev model, then Opus) are never mixed together.
    by_model: dict[str, list[dict]] = {}
    for t in trials:
        by_model.setdefault(t["model_id"], []).append(t)
    models = [model_stats(ts) for ts in by_model.values()]
    order = {"llm": 0, "jev": 1, "luna": 2, "clef": 3}
    models.sort(key=lambda m: order.get(m["model_key"], 9))
    return {
        "test_set": test_set,
        "sessions": used_sessions,
        "trial_count": len(trials),
        "puzzle_count": len({(t["puzzle_id"]) for t in trials}),
        "models": models,
        "answers": answer_questions(models),
    }


def _name(m: dict) -> str:
    return m["model_name"]


def _recommendation(llm: dict, dec: dict) -> str:
    if llm["success_rate"] > dec["success_rate"]:
        return ("Multi-step planning tasks where a wrong move is costly favour the frontier LLM. A hybrid agent "
                "(the LLM plans, a fast decision model handles simple, well-defined single choices) keeps most "
                "of the quality at lower latency and cost.")
    if dec["success_rate"] > llm["success_rate"]:
        return ("The decision model matched or beat the LLM's quality at a fraction of the latency, so it is "
                "the better default here; an LLM fallback only adds value on states it fails.")
    return ("Both solved equally often, so latency and cost decide: prefer the decision model and escalate to "
            "the LLM (a hybrid) only when it is not confident.")


def answer_questions(models: list[dict]) -> list[dict]:
    """Evidence-based answers to the five questions in the assignment."""
    if not models:
        return []
    timed = [m for m in models if m["avg_move_latency_s"] is not None]
    fastest = min(timed, key=lambda m: m["avg_move_latency_s"]) if timed else None
    best_rate = max(m["success_rate"] for m in models)
    top_solvers = [m for m in models if m["success_rate"] == best_rate]
    gapped = [m for m in models if m["avg_optimality_gap"] is not None]
    best_gap = min(gapped, key=lambda m: (m["avg_optimality_gap"], -m["success_rate"])) if gapped else None
    best_gappers = [m for m in gapped if best_gap and abs(m["avg_optimality_gap"] - best_gap["avg_optimality_gap"]) < 1e-9]
    out = []

    if fastest:
        out.append({"q": "Which model is fastest in terms of making decisions?",
                    "a": f"{_name(fastest)}: {fastest['avg_move_latency_s']:.2f} s average per move "
                         f"(median {fastest['median_move_latency_s']:.2f} s)."})
    out.append({"q": "Which model achieved the highest solve rate?",
                "a": ", ".join(_name(m) for m in top_solvers) +
                     f": {best_rate:.0f}% ({top_solvers[0]['solved']}/{top_solvers[0]['trials']} puzzles solved)."})
    if best_gap:
        out.append({"q": "Which model found the shortest solutions, and how close to the optimum?",
                    "a": ", ".join(f"{_name(m)} ({m['optimal_solves']}/{m['solved']} solves optimal)" for m in best_gappers)
                         + f": average optimality gap {best_gap['avg_optimality_gap']:+.2f} moves on solved puzzles"
                         + (" (exact optimum by BFS)." if best_gap["gap_is_exact"] else " (vs. scramble-length upper bound).")})
    else:
        out.append({"q": "Which model found the shortest solutions, and how close to the optimum?",
                    "a": "No model solved a puzzle, so no optimality gap can be computed."})
    if fastest:
        quality_best = fastest in best_gappers and fastest["success_rate"] == best_rate
        out.append({"q": "Did the fastest model also achieve the best solution quality?",
                    "a": ("Yes. " if quality_best else "No. ") +
                         f"{_name(fastest)} was fastest with a {fastest['success_rate']:.0f}% solve rate"
                         + (f" and gap {fastest['avg_optimality_gap']:+.2f}." if fastest["avg_optimality_gap"] is not None
                            else " and no solved puzzles to measure a gap on.")})
    llm = next((m for m in models if m["category"] == "llm"), None)
    dec = [m for m in models if m["category"] == "decision"]
    if llm and dec:
        best_dec = max(dec, key=lambda m: (m["success_rate"], -(m["avg_move_latency_s"] or 1e9)))
        ratio = (llm["avg_move_latency_s"] / best_dec["avg_move_latency_s"]) if llm["avg_move_latency_s"] and best_dec["avg_move_latency_s"] else None
        out.append({"q": "Fastest decision model, frontier LLM, or a hybrid agent for real-world use?",
                    "a": f"Evidence: {_name(llm)} solved {llm['success_rate']:.0f}% at {llm['avg_move_latency_s'] or 0:.2f} s/move; "
                         f"the best decision model ({_name(best_dec)}) solved {best_dec['success_rate']:.0f}% at "
                         f"{best_dec['avg_move_latency_s'] or 0:.2f} s/move"
                         + (f" ({ratio:.0f}x faster per decision)." if ratio else ".")
                         + " " + _recommendation(llm, best_dec)})
    return out
