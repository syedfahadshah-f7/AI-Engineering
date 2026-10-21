"""Pre-flight check.

    python -m app.check            # dry run: no API requests at all
    python -m app.check --live     # one request per model (cached, so not wasted)

The dry run prints the provider, models, rules, the experiment puzzle, the
persistent budget and the cache. It never calls OpenRouter.

--live sends exactly the *first* request of the real experiment (same puzzle,
same observation) for each model. The responses go into the persistent cache,
so the real run reuses them instead of paying for them again. Every live
request counts toward the persistent budget.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx

from .agents.registry import build_agent
from .benchmark.runner import SessionManager
from .config import get_settings
from .cube.scramble import make_puzzle
from .gateway import Gateway, setup_logging
from .prompts import build_observation


async def main(live: bool, test_set: str, seed: int) -> int:
    s = get_settings()
    setup_logging(s.log_dir)
    mgr = SessionManager(s)
    print(f"Provider: {s.active_provider}    Student: {s.student_name} ({s.roll_number})")
    print(f"Rules: move limit {s.max_moves}, transport retries {s.max_transport_retries}, "
          f"invalid re-asks {s.max_invalid_retries}, cache {'on' if s.cache_enabled else 'OFF'}")
    for spec in s.models:
        cap = f"cap {spec.call_cap} calls" if spec.call_cap is not None else "no call cap"
        print(f"  [{spec.key:4}] {spec.name:<24} {spec.model_id:<32} moves<={spec.move_limit:<3} {cap}")

    puzzle = make_puzzle(test_set, seed)
    print(f"\nExperiment puzzle {puzzle.id}: scramble {' '.join(puzzle.scramble)} | "
          f"exact optimum {puzzle.optimal_moves} moves: {' '.join(puzzle.optimal_solution or [])}")

    b = mgr.budget()
    print(f"\nPersistent OpenRouter usage: {b['openrouter']['total_calls']}/{s.total_call_cap} requests, "
          f"${b['openrouter']['cost_usd']:.4f}")
    for mid, m in b["openrouter"].get("models", {}).items():
        print(f"  {mid:<32} {m['calls']} calls  ${m['cost_usd']:.4f}")
    print(f"Cache: {json.dumps(b['cache'])}")

    if s.active_provider == "mock":
        print("\nMOCK provider: simulated models, no API requests. Set PROVIDER=openrouter in backend/.env for the real run.")
        return 0
    if not s.openrouter_api_key.strip():
        print("\nERROR: PROVIDER=openrouter but OPENROUTER_API_KEY is empty in backend/.env")
        return 1

    if not live:
        print("\nDry run finished: no API requests were made. Use --live to send one cached request per model.")
        return 0

    print(f"\n--live will send up to {len(s.models)} OpenRouter requests (they count toward the budget, "
          "but they are cached and reused by the real run).")
    if input("Type YES to continue: ").strip() != "YES":
        print("Cancelled.")
        return 1
    ok = True
    async with httpx.AsyncClient() as client:
        gw = Gateway(s, client, mgr.cache, mgr.ledger)
        for spec in s.models:
            obs = build_observation(puzzle.state, [], spec.move_limit, s.recent_moves_window)
            d = await build_agent(spec, s, gw).decide(obs)
            ok &= d.move is not None
            src = "cache" if d.cached else "live "
            conf = f" conf={d.confidence:.2f}" if d.confidence is not None else ""
            print(f"[{'OK ' if d.move else 'ERR'}] {spec.name:<24} {src} move={d.move!s:<3} "
                  f"latency={d.latency_s:.2f}s{conf} cost=${d.cost or 0:.5f}")
            if d.error:
                print(f"      {d.error_kind}: {d.error}")
    print("\nAll models responded." if ok else "\nSome models failed; see the errors above and logs/api.log.")
    return 0 if ok else 2


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true", help="send one (cached) request per model")
    ap.add_argument("--test-set", default="three")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.live, a.test_set, a.seed)))
