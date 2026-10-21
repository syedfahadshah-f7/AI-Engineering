import type { MoveRecord, Puzzle, RaceEvent, SessionSummary, TrialResult } from "./api";

export type PanelStatus = "idle" | "waiting" | "thinking" | "done";

export interface PanelState {
  status: PanelStatus;
  moves: MoveRecord[];
  invalid: { move_index: number; kind: string; error: string }[];
  result: TrialResult | null;
  startedAt: number | null; // client clock (ms) when the race started
  rank: number | null;
}

export interface RaceState {
  session: SessionSummary | null;
  sessionStatus: "idle" | "running" | "completed" | "cancelled" | "failed";
  puzzle: Puzzle | null;
  raceIndex: number;
  raceTotal: number;
  panels: Record<string, PanelState>;
  lastSeq: number;
  error: string | null;
  finishedRaces: number;
  modelKeys: string[];
}

export const emptyPanel = (): PanelState => ({
  status: "idle",
  moves: [],
  invalid: [],
  result: null,
  startedAt: null,
  rank: null,
});

export const initialRace: RaceState = {
  session: null,
  sessionStatus: "idle",
  puzzle: null,
  raceIndex: 0,
  raceTotal: 0,
  panels: {},
  lastSeq: -1,
  error: null,
  finishedRaces: 0,
  modelKeys: [],
};

export type RaceAction =
  | { kind: "event"; event: RaceEvent }
  | { kind: "reset"; session: SessionSummary; modelKeys: string[] }
  | { kind: "preview"; puzzle: Puzzle; modelKeys: string[] };

function patch(state: RaceState, key: string, fn: (p: PanelState) => PanelState): RaceState {
  const prev = state.panels[key] ?? emptyPanel();
  return { ...state, panels: { ...state.panels, [key]: fn(prev) } };
}

export function raceReducer(state: RaceState, action: RaceAction): RaceState {
  if (action.kind === "reset") {
    const panels: Record<string, PanelState> = {};
    for (const k of action.modelKeys) panels[k] = { ...emptyPanel(), status: "waiting" };
    return { ...initialRace, session: action.session, sessionStatus: "running", modelKeys: action.modelKeys, panels };
  }
  if (action.kind === "preview") {
    if (state.sessionStatus === "running") return state;
    const panels: Record<string, PanelState> = {};
    for (const k of action.modelKeys) panels[k] = emptyPanel();
    return { ...initialRace, puzzle: action.puzzle, panels, modelKeys: action.modelKeys };
  }

  const ev = action.event;
  if (ev.seq <= state.lastSeq) return state; // replayed after an SSE reconnect
  state = { ...state, lastSeq: ev.seq };
  const now = performance.now();

  switch (ev.type) {
    case "session_started":
      return { ...state, session: ev.session, sessionStatus: "running" };
    case "race_started": {
      const panels: Record<string, PanelState> = {};
      for (const k of state.modelKeys) {
        // The clock starts at the model's first request (models may run one after another).
        panels[k] = { ...emptyPanel(), status: "waiting", startedAt: null };
      }
      return { ...state, puzzle: ev.puzzle, raceIndex: ev.index, raceTotal: ev.total, panels, error: null };
    }
    case "thinking":
      return patch(state, ev.model, (p) => ({
        ...p,
        status: "thinking",
        startedAt: p.startedAt ?? now - ev.elapsed_s * 1000,
      }));
    case "move": {
      const { type: _t, model, seq: _s, t: _tt, ...rec } = ev;
      return patch(state, model, (p) => ({
        ...p,
        moves: [...p.moves, rec as MoveRecord],
        startedAt: p.startedAt ?? now - ev.elapsed_s * 1000,
      }));
    }
    case "invalid":
      return patch(state, ev.model, (p) => ({
        ...p,
        invalid: [...p.invalid, { move_index: ev.move_index, kind: ev.kind, error: ev.error }],
      }));
    case "finished":
      return patch(state, ev.model, (p) => ({ ...p, status: "done", result: ev.result }));
    case "race_finished": {
      let next = { ...state, finishedRaces: state.finishedRaces + 1 };
      ev.ranking.forEach((key, i) => {
        next = patch(next, key, (p) => ({ ...p, rank: i + 1 }));
      });
      return next;
    }
    case "error":
      return { ...state, error: ev.message };
    case "session_finished":
      return { ...state, sessionStatus: ev.status as RaceState["sessionStatus"] };
  }
  return state;
}
