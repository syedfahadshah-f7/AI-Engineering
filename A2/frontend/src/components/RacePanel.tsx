import { useEffect, useMemo, useState } from "react";
import type { ModelSpec, Sticker } from "../api";
import { MODEL_COLOURS, MODEL_INITIAL, STATUS_LABEL, clock, ordinal, secs } from "../format";
import type { PanelState } from "../race";
import Cube3D from "./Cube3D";
import CubeNet from "./CubeNet";

const HISTORY_SHOWN = 16; // one line; the full history is in the saved results

interface Props {
  spec: ModelSpec;
  panel: PanelState;
  startState: string;
  stickers: Sticker[];
  maxMoves: number;
  optimal: number | null;
}

function useTicker(active: boolean) {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    let raf = 0;
    const loop = () => {
      setTick((t) => t + 1);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [active]);
}

export default function RacePanel({ spec, panel, startState, stickers, maxMoves, optimal }: Props) {
  const running = panel.status === "waiting" || panel.status === "thinking";
  useTicker(running && panel.startedAt != null);

  const elapsed = panel.result
    ? panel.result.total_time_s
    : panel.startedAt != null
      ? (performance.now() - panel.startedAt) / 1000
      : 0;
  const steps = useMemo(() => panel.moves.map((m) => ({ move: m.move, state: m.state })), [panel.moves]);
  const currentState = panel.moves.length ? panel.moves[panel.moves.length - 1].state : startState;
  const last = panel.moves[panel.moves.length - 1];
  const avgLatency = panel.moves.length
    ? panel.moves.reduce((a, m) => a + m.latency_s, 0) / panel.moves.length
    : null;
  const result = panel.result;
  const solved = result?.solved;
  const isLLM = spec.category === "llm";

  const apiCalls = panel.moves.reduce((a, m) => a + m.api_calls, 0);
  const cacheHits = panel.moves.filter((m) => m.cached).length;

  let statusText = "ready";
  if (panel.status === "waiting") statusText = "waiting..";
  if (panel.status === "thinking") statusText = isLLM ? "thinking.." : "deciding..";
  if (result) statusText = solved ? "SOLVED ✓" : "NOT SOLVED";

  return (
    <article className={`panel ${solved ? "panel--won" : ""} ${panel.rank === 1 && solved ? "panel--first" : ""}`}>
      <header className="panel__head">
        <span className="logo" style={{ background: MODEL_COLOURS[spec.key] }} aria-hidden>
          {MODEL_INITIAL[spec.key] ?? spec.name[0]}
        </span>
        <div className="panel__title">
          <h2>{spec.name}</h2>
          <code>{spec.model_id}</code>
        </div>
        <span className={`badge ${isLLM ? "badge--llm" : "badge--dm"}`}>{isLLM ? "LLM" : "DECISION MODEL"}</span>
      </header>

      <div className="panel__body">
        <div className="panel__cube">
          {stickers.length === 54 && <Cube3D stickers={stickers} initialState={startState} steps={steps} />}
          {panel.rank != null && result && (
            <div className={`medal medal--${Math.min(panel.rank, 4)}`}>
              {panel.rank}
              <sup>{ordinal(panel.rank).toUpperCase()}</sup>
            </div>
          )}
          {result && !solved && <div className="ribbon">{STATUS_LABEL[result.status] ?? result.status}</div>}
          <div className="panel__net">
            <CubeNet state={currentState} />
          </div>
        </div>

        <div className={`stats ${result ? (solved ? "stats--ok" : "stats--bad") : ""}`}>
          <div className="stat">
            <span className="stat__label">TIME</span>
            <span className="stat__value mono">{clock(elapsed)}</span>
          </div>
          <div className="stat">
            <span className="stat__label">MOVES</span>
            <span className="stat__value">
              {panel.moves.length}
              <small> / {spec.move_limit ?? maxMoves}</small>
            </span>
          </div>
          <div className="stat stat--small">
            <span className="stat__label">AVG / MOVE</span>
            <span className="stat__value mono">{secs(avgLatency)}</span>
          </div>
          <div className="stat stat--small">
            <span className="stat__label">API CALLS · CACHE HITS</span>
            <span className="stat__value mono">
              {result ? result.api_calls : apiCalls} · {result ? result.cache_hits : cacheHits}
            </span>
          </div>
          {result && solved && optimal != null && (
            <div className="stat stat--small">
              <span className="stat__label">OPTIMAL GAP</span>
              <span className="stat__value">{result.optimality_gap === 0 ? "0 (optimal)" : `+${result.optimality_gap}`}</span>
            </div>
          )}
          <div className={`stat__status ${panel.status === "thinking" ? "pulse" : ""}`}>{statusText}</div>
        </div>
      </div>

      <footer className="panel__foot">
        <div className="current">
          <span className="current__label">Current move</span>
          <span className="current__move">{last?.move ?? "—"}</span>
          {last && (
            <span className="current__meta">
              {last.cached ? `cache ${((last.cache_time_s ?? 0) * 1000).toFixed(1)} ms (live was ${secs(last.latency_s)})` : `live ${secs(last.latency_s)}`}
              {last.confidence != null && ` · conf ${(last.confidence * 100).toFixed(0)}%`}
            </span>
          )}
          {panel.invalid.length > 0 && (
            <span className="invalid-count" title={panel.invalid.map((i) => `#${i.move_index} ${i.kind}: ${i.error}`).join("\n")}>
              ⚠ {panel.invalid.length} invalid
            </span>
          )}
        </div>
        <ol className="history" aria-label="Move history">
          {panel.moves.length > HISTORY_SHOWN && <li className="history__more">+{panel.moves.length - HISTORY_SHOWN} earlier</li>}
          {panel.moves.slice(-HISTORY_SHOWN).map((m) => (
            <li
              key={m.index}
              className={m.cached ? "is-cached" : ""}
              title={`#${m.index} ${m.move} · ${m.cached ? "from cache" : "live"} · ${m.latency_s.toFixed(2)} s`}
            >
              {m.move}
            </li>
          ))}
        </ol>
      </footer>
    </article>
  );
}
