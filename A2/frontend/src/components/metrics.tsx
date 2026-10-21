import type { ModelStats } from "../api";
import { num, secs, signed } from "../format";
import BarChart from "./BarChart";

// The five required benchmark statistics (assignment section 3C).
export function MetricCharts({ models, compact }: { models: ModelStats[]; compact?: boolean }) {
  const bars = (pick: (m: ModelStats) => number | null, fmt: (v: number | null) => string, detail?: (m: ModelStats) => string) =>
    models.map((m) => ({ key: m.model_id, colourKey: m.model_key, label: m.model_name, value: pick(m), display: fmt(pick(m)), detail: detail?.(m) }));

  return (
    <div className={`charts ${compact ? "charts--compact" : ""}`}>
      <BarChart
        compact={compact}
        title="Per-move average latency"
        subtitle="seconds per decision · lower is faster"
        better="lower"
        bars={bars((m) => m.avg_move_latency_s, (v) => secs(v), (m) =>
          `live API avg ${secs(m.avg_live_latency_s)} · cache avg ${m.avg_cache_time_s == null ? "—" : (m.avg_cache_time_s * 1000).toFixed(1) + " ms"} · ${m.api_calls} API calls, ${m.cache_hits} cache hits`)}
      />
      <BarChart
        compact={compact}
        title="Total solve time"
        subtitle="mean wall-clock per puzzle (until solved or limit)"
        better="lower"
        bars={bars((m) => m.avg_total_time_s, (v) => secs(v, 1), (m) => `sum over ${m.trials} puzzles: ${secs(m.total_time_s, 1)}`)}
      />
      <BarChart
        compact={compact}
        title="Total number of moves"
        subtitle="moves executed across all puzzles"
        better="lower"
        bars={bars((m) => m.total_moves, (v) => (v == null ? "—" : String(v)), (m) =>
          `avg ${num(m.avg_moves)} per puzzle · avg ${num(m.avg_moves_solved)} when solved`)}
      />
      <BarChart
        compact={compact}
        title="Success rate"
        subtitle="% of puzzles solved within the move limit"
        better="higher"
        max={100}
        bars={bars((m) => m.success_rate, (v) => (v == null ? "—" : `${v.toFixed(0)}%`), (m) => `${m.solved} of ${m.trials} solved`)}
      />
      <BarChart
        compact={compact}
        title="Optimality gap"
        subtitle="model moves − exact shortest moves (solved puzzles) · 0 = optimal"
        better="lower"
        bars={bars((m) => m.avg_optimality_gap, (v) => signed(v), (m) =>
          m.avg_optimality_gap == null ? "no solved puzzles" : `${m.optimal_solves} optimal solve(s) of ${m.solved}`)}
      />
    </div>
  );
}

export function MetricsTable({ models, compact }: { models: ModelStats[]; compact?: boolean }) {
  return (
    <div className="table-wrap">
      <table className={`metrics ${compact ? "metrics--compact" : ""}`}>
        <thead>
          <tr>
            <th>Model</th>
            {!compact && <th>Type</th>}
            <th>Avg latency / move</th>
            <th>Avg total time</th>
            <th>Total moves</th>
            <th>Success rate</th>
            <th>Optimality gap</th>
            <th>Invalid outputs</th>
            <th>API calls</th>
            <th>Cache hits</th>
            {!compact && <th>Live latency</th>}
            {!compact && <th>Cache time</th>}
            {!compact && <th>Retries</th>}
            <th>Cost (USD)</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr key={m.model_id}>
              <th scope="row">
                {m.model_name}
                {!compact && <code>{m.model_id}</code>}
              </th>
              {!compact && <td>{m.category === "llm" ? "Frontier LLM" : "Decision model"}</td>}
              <td className="mono">{secs(m.avg_move_latency_s)}</td>
              <td className="mono">{secs(m.avg_total_time_s, 1)}</td>
              <td className="mono">{m.total_moves}</td>
              <td className="mono">
                {m.success_rate.toFixed(0)}% ({m.solved}/{m.trials})
              </td>
              <td className="mono">{signed(m.avg_optimality_gap)}</td>
              <td className="mono">{m.invalid_outputs}</td>
              <td className="mono">{m.api_calls}</td>
              <td className="mono">{m.cache_hits}</td>
              {!compact && <td className="mono">{secs(m.avg_live_latency_s)}</td>}
              {!compact && (
                <td className="mono">{m.avg_cache_time_s == null ? "—" : `${(m.avg_cache_time_s * 1000).toFixed(1)} ms`}</td>
              )}
              {!compact && <td className="mono">{m.retries}</td>}
              <td className="mono">{m.cost_usd ? `$${m.cost_usd.toFixed(4)}` : "$0"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
