"""Every model request goes through the Gateway.

For each request it, in order:
  1. checks the persistent response cache, and returns the stored response on a hit;
  2. on a miss, reserves one call in the persistent budget ledger *before*
     sending. The reservation is refused once a cap is reached, so the backend
     can never exceed the limits;
  3. logs the request (before and after) to logs/api.log;
  4. sends it, measures live latency, and stores successful responses in the cache.

The cache (data/cache.json) and the ledger (data/usage.json) are plain JSON
files written atomically. They survive restarts and are never reset by the app.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .config import ModelSpec, Settings

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 524, 529}

log = logging.getLogger("api")


def setup_logging(log_dir: Path) -> None:
    if log.handlers:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(log_dir / "api.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(sh)
    log.setLevel(logging.INFO)
    log.propagate = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    # On Windows, antivirus/indexers can briefly lock the target and make the
    # replace fail with PermissionError. That must never crash a trial after a
    # paid request, so retry briefly before giving up.
    for attempt in range(8):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.05 * (attempt + 1))


def request_key(provider: str, path: str, payload: dict) -> str:
    """Same provider + endpoint + model + request body  =>  same key."""
    canon = json.dumps({"provider": provider, "path": path, "payload": payload}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._dirty = False  # hit counters changed in memory but not yet written
        self._data: dict[str, dict] = {}
        if path.exists():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                # Never silently drop a cache: keep the broken file for inspection.
                path.rename(path.with_suffix(f".corrupt-{int(time.time())}.json"))
                self._data = {}

    def get(self, key: str) -> dict | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is not None:
                # Hit counters are flushed lazily (put/flush), so a lookup is a
                # pure in-memory read and its measured time is the real cache time.
                entry["hits"] = entry.get("hits", 0) + 1
                entry["last_hit_at"] = _now()
                self._dirty = True
            return entry

    def put(self, key: str, entry: dict) -> None:
        with self._lock:
            self._data[key] = {**entry, "hits": 0, "created_at": _now()}
            _atomic_write(self.path, self._data)
            self._dirty = False

    def flush(self) -> None:
        with self._lock:
            if self._dirty:
                _atomic_write(self.path, self._data)
                self._dirty = False

    def __len__(self) -> int:
        return len(self._data)

    def stats(self) -> dict:
        with self._lock:
            by_provider: dict[str, int] = {}
            for e in self._data.values():
                by_provider[e.get("provider", "?")] = by_provider.get(e.get("provider", "?"), 0) + 1
            return {"entries": len(self._data), "by_provider": by_provider,
                    "total_hits": sum(e.get("hits", 0) for e in self._data.values())}


class BudgetExceeded(Exception):
    pass


class BudgetLedger:
    """Persistent count of live requests per provider and model."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._data: dict = {"providers": {}}
        if path.exists():
            self._data = json.loads(path.read_text(encoding="utf-8"))  # fail loudly if corrupt

    def _bucket(self, provider: str) -> dict:
        return self._data["providers"].setdefault(provider, {"total_calls": 0, "cost_usd": 0.0, "models": {}})

    def reserve(self, spec: ModelSpec, total_cap: int | None) -> tuple[int, int]:
        """Count one request before it is sent. Raises BudgetExceeded instead of
        exceeding a cap. Returns (calls for this model, total calls) after counting."""
        with self._lock:
            b = self._bucket(spec.provider)
            m = b["models"].setdefault(spec.model_id, {"calls": 0, "cost_usd": 0.0, "slot": spec.key})
            if spec.call_cap is not None and m["calls"] >= spec.call_cap:
                raise BudgetExceeded(f"{spec.name} reached its cap of {spec.call_cap} API requests")
            if total_cap is not None and b["total_calls"] >= total_cap:
                raise BudgetExceeded(f"Overall cap of {total_cap} API requests reached")
            m["calls"] += 1
            b["total_calls"] += 1
            b["last_call_at"] = _now()
            _atomic_write(self.path, self._data)
            return m["calls"], b["total_calls"]

    def add_cost(self, spec: ModelSpec, cost: float | None) -> None:
        if not cost:
            return
        with self._lock:
            b = self._bucket(spec.provider)
            b["cost_usd"] += cost
            b["models"].setdefault(spec.model_id, {"calls": 0, "cost_usd": 0.0, "slot": spec.key})["cost_usd"] += cost
            _atomic_write(self.path, self._data)

    def snapshot(self, provider: str) -> dict:
        with self._lock:
            b = self._data["providers"].get(provider, {"total_calls": 0, "cost_usd": 0.0, "models": {}})
            return json.loads(json.dumps(b))


@dataclass
class GatewayResult:
    data: dict
    cached: bool
    live_latency_s: float | None  # measured now (live requests only)
    cache_time_s: float | None  # time to serve from cache (hits only)
    model_latency_s: float  # live latency, or the stored original live latency on a hit
    api_calls: int  # live HTTP requests sent for this result
    cost_usd: float  # actual cost of the live requests (0 on a hit)


class TransportError(Exception):
    def __init__(self, message: str, api_calls: int, latency_s: float, kind: str = "api_error"):
        super().__init__(message)
        self.api_calls = api_calls
        self.latency_s = latency_s
        self.kind = kind  # api_error | budget


class Gateway:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None,
                 cache: ResponseCache, ledger: BudgetLedger):
        self.settings = settings
        self.client = client
        self.cache = cache
        self.ledger = ledger

    def _endpoint(self, spec: ModelSpec, path: str) -> tuple[str, dict[str, str]]:
        return (self.settings.openrouter_base_url.rstrip("/") + path,
                {"Authorization": f"Bearer {self.settings.openrouter_api_key}",
                 "Content-Type": "application/json", "X-Title": "Rubik's Cube Race"})

    async def post(self, spec: ModelSpec, path: str, payload: dict, cost_of=lambda d: None) -> GatewayResult:
        s = self.settings
        key = request_key(spec.provider, path, payload)

        if s.cache_enabled:
            t0 = time.perf_counter()
            hit = await asyncio.to_thread(self.cache.get, key)
            if hit is not None:
                dt = time.perf_counter() - t0
                log.info(f"CACHE HIT  | {spec.provider} | {spec.model_id} | key={key[:12]} | "
                         f"served in {dt * 1000:.1f} ms (original live latency {hit['live_latency_s']:.3f} s)")
                return GatewayResult(hit["response"], True, None, dt, hit["live_latency_s"], 0, 0.0)
            log.info(f"CACHE MISS | {spec.provider} | {spec.model_id} | key={key[:12]}")

        assert self.client is not None
        url, headers = self._endpoint(spec, path)
        calls = 0
        latency = 0.0
        last_error = "unknown error"
        for attempt in range(s.max_transport_retries + 1):
            try:
                model_calls, total = await asyncio.to_thread(self.ledger.reserve, spec, s.total_call_cap)
            except BudgetExceeded as exc:
                log.warning(f"BLOCKED    | {spec.provider} | {spec.model_id} | {exc}")
                raise TransportError(str(exc), calls, latency, kind="budget") from exc
            budget = f"call {model_calls}/{spec.call_cap} for model, {total}/{s.total_call_cap} total"
            calls += 1
            log.info(f"REQUEST    | {spec.provider} | {spec.model_id} | key={key[:12]} | attempt {attempt + 1} | {budget}")
            t0 = time.perf_counter()
            try:
                resp = await self.client.post(url, json=payload, headers=headers, timeout=s.request_timeout_s)
                latency = time.perf_counter() - t0
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                latency = time.perf_counter() - t0
                last_error = f"{type(exc).__name__}: {exc}"
                log.error(f"FAILED     | {spec.provider} | {spec.model_id} | {latency:.3f} s | {last_error}")
            else:
                if resp.status_code < 400:
                    try:
                        data = resp.json()
                    except ValueError:
                        last_error = f"Non-JSON response body (HTTP {resp.status_code})"
                        log.error(f"FAILED     | {spec.provider} | {spec.model_id} | {latency:.3f} s | {last_error}")
                        break
                    cost = cost_of(data) or 0.0
                    await asyncio.to_thread(self.ledger.add_cost, spec, cost)
                    log.info(f"RESPONSE   | {spec.provider} | {spec.model_id} | HTTP {resp.status_code} | "
                             f"live latency {latency:.3f} s | cost ${cost:.6f}")
                    if s.cache_enabled:
                        await asyncio.to_thread(self.cache.put, key, {
                            "provider": spec.provider, "model": spec.model_id, "path": path,
                            "response": data, "live_latency_s": latency, "cost_usd": cost,
                        })
                    return GatewayResult(data, False, latency, None, latency, calls, cost)
                last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                log.error(f"FAILED     | {spec.provider} | {spec.model_id} | {latency:.3f} s | {last_error}")
                if resp.status_code not in RETRYABLE_STATUS:
                    break
            if attempt < s.max_transport_retries:
                await asyncio.sleep(1.5 * (2**attempt))
        raise TransportError(last_error, calls, latency)
