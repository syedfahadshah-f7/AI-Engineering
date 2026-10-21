// Typed client for the FastAPI backend. All OpenRouter calls happen on the
// server; the browser never sees the API key.

export interface ModelSpec {
  key: string;
  model_id: string;
  name: string;
  category: "llm" | "decision";
  interface: "chat" | "decisions";
  provider: Provider;
  move_limit: number;
  call_cap: number | null;
}

export type Provider = "mock" | "openrouter";

export interface AppConfig {
  student_name: string;
  roll_number: string;
  provider: Provider;
  mock: boolean;
  openrouter_max_puzzles: number;
  models: ModelSpec[];
  test_sets: Record<string, { min: number; max: number }>;
  rules: {
    max_moves: number;
    recent_moves_window: number;
    request_timeout_s: number;
    max_transport_retries: number;
    max_invalid_retries: number;
    trial_time_limit_s: number;
    llm_reasoning_effort: string;
    total_call_cap: number | null;
    cache_enabled: boolean;
    metric: string;
  };
  solved_state: string;
}

export interface Sticker {
  index: number;
  face: string;
  position: [number, number, number];
  normal: [number, number, number];
}

export interface Puzzle {
  id: string;
  test_set: string;
  seed: number;
  scramble: string[];
  state: string;
  optimal_moves: number | null;
  optimal_solution: string[] | null;
  optimal_exact: boolean;
  reference_moves: number;
}

export interface MoveRecord {
  index: number;
  move: string;
  latency_s: number;
  live_latency_s: number | null;
  cache_time_s: number | null;
  cached: boolean;
  api_calls: number;
  cost_usd: number;
  confidence: number | null;
  top_probabilities: Record<string, number>;
  elapsed_s: number;
  state: string;
}

export type TrialStatus = "solved" | "move_limit" | "time_limit" | "invalid_output" | "api_error" | "budget_limit";

export interface TrialResult {
  model_key: string;
  model_name: string;
  status: TrialStatus;
  solved: boolean;
  error: string | null;
  move_limit: number;
  move_count: number;
  api_calls: number;
  cache_hits: number;
  invalid_count: number;
  api_error_count: number;
  retries: number;
  avg_move_latency_s: number | null;
  total_time_s: number;
  optimal_moves: number | null;
  reference_moves: number;
  optimality_gap: number | null;
  facelets_correct: number;
  cost_usd: number;
}

export type RaceEvent = { seq: number; t: number } & (
  | { type: "session_started"; session: SessionSummary; rules: Record<string, unknown> }
  | { type: "race_started"; index: number; total: number; puzzle: Puzzle }
  | { type: "thinking"; model: string; move_index: number; elapsed_s: number }
  | ({ type: "move"; model: string } & MoveRecord)
  | { type: "invalid"; model: string; move_index: number; kind: string; error: string; elapsed_s: number }
  | { type: "finished"; model: string; result: TrialResult }
  | { type: "race_finished"; index: number; puzzle_id: string; ranking: string[]; budget: Budget }
  | { type: "error"; message: string }
  | { type: "session_finished"; status: string }
);

export interface SessionSummary {
  id: string;
  test_set: string;
  seeds: number[];
  provider: Provider;
  mock: boolean;
  status: string;
  created_at: string;
  puzzle_count: number;
}

export interface ModelStats {
  model_key: string;
  model_name: string;
  model_id: string;
  category: string;
  provider: Provider;
  trials: number;
  solved: number;
  success_rate: number;
  avg_move_latency_s: number | null;
  median_move_latency_s: number | null;
  p95_move_latency_s: number | null;
  avg_total_time_s: number;
  total_time_s: number;
  avg_solve_time_s: number | null;
  total_moves: number;
  avg_moves: number;
  avg_moves_solved: number | null;
  avg_optimality_gap: number | null;
  gap_is_exact: boolean;
  optimal_solves: number;
  invalid_outputs: number;
  api_errors: number;
  retries: number;
  calls: number;
  api_calls: number;
  cache_hits: number;
  avg_live_latency_s: number | null;
  avg_cache_time_s: number | null;
  cost_usd: number;
  statuses: Record<string, number>;
}

export interface StatsResponse {
  test_set: string | null;
  sessions: string[];
  trial_count: number;
  puzzle_count: number;
  models: ModelStats[];
  answers: { q: string; a: string }[];
  provider: Provider;
  mock: boolean;
}

export interface Budget {
  provider: Provider;
  capped: boolean;
  total_cap: number;
  openrouter: {
    total_calls: number;
    cost_usd: number;
    models: Record<string, { calls: number; cost_usd: number; slot: string }>;
  };
  caps: Record<string, number | null>;
  cache: { entries: number; by_provider: Record<string, number>; total_hits: number };
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  config: () => fetch("/api/config").then((r) => json<AppConfig>(r)),
  geometry: () => fetch("/api/cube/geometry").then((r) => json<{ stickers: Sticker[] }>(r)),
  preview: (testSet: string, seed: number) =>
    fetch(`/api/puzzles/preview?test_set=${testSet}&seed=${seed}`).then((r) => json<Puzzle>(r)),
  startSession: (body: { test_set: string; count: number; start_seed: number }) =>
    fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<SessionSummary>(r)),
  cancel: (id: string) => fetch(`/api/sessions/${id}/cancel`, { method: "POST" }).then((r) => json(r)),
  sessions: () => fetch("/api/sessions").then((r) => json<{ active: SessionSummary | null; sessions: SessionSummary[] }>(r)),
  budget: () => fetch("/api/budget").then((r) => json<Budget>(r)),
  stats: (testSet: string, provider: Provider, sessions?: string[]) => {
    const q = new URLSearchParams({ test_set: testSet, provider });
    if (sessions?.length) q.set("sessions", sessions.join(","));
    return fetch(`/api/stats?${q}`).then((r) => json<StatsResponse>(r));
  },
  events: (id: string, onEvent: (e: RaceEvent) => void, onDone: () => void) => {
    const es = new EventSource(`/api/sessions/${id}/events`);
    es.onmessage = (m) => {
      const ev = JSON.parse(m.data) as RaceEvent;
      onEvent(ev);
      if (ev.type === "session_finished") {
        es.close();
        onDone();
      }
    };
    es.onerror = () => {
      // EventSource auto-reconnects; the server replays from the start and
      // the reducer ignores events it has already applied (by seq).
    };
    return () => es.close();
  },
};
