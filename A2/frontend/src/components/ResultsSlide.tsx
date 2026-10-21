import { useRef } from "react";
import type { AppConfig, StatsResponse } from "../api";
import { MetricCharts, MetricsTable } from "./metrics";

// The closing slide for the demo recording: all five statistics, the answers
// to the assignment's questions, and the student's identity.
export default function ResultsSlide({ stats, config }: { stats: StatsResponse | null; config: AppConfig }) {
  const ref = useRef<HTMLDivElement>(null);
  const fullscreen = () => ref.current?.requestFullscreen?.();

  return (
    <section className="slide-wrap">
      <div className="slide-actions">
        <button className="btn" onClick={fullscreen}>
          Present full screen
        </button>
      </div>
      <div className="slide" ref={ref}>
        <header className="slide__head">
          <div>
            <p className="slide__kicker">AI Engineering · Assignment 02 · Rubik's Cube Race</p>
            <h1>Statistical Benchmark Results</h1>
            {stats && (
              <p className="slide__sub">
                {stats.provider === "openrouter" ? "OpenRouter (live API)" : "MOCK DATA (simulated)"} ·{" "}
                {stats.test_set === "three" ? "start exactly 3 moves from solved" : `${stats.test_set} test set`} ·{" "}
                {stats.puzzle_count} puzzle(s) × {stats.models.length} models = {stats.trial_count} trials · max{" "}
                {config.rules.max_moves} moves
                {stats.provider === "openrouter" && " (Claude max 5 requests)"} · HTM metric · exact optimum by BFS ·
                persistent response cache
              </p>
            )}
          </div>
          <div className="slide__id">
            <span>{config.student_name}</span>
            <strong>{config.roll_number}</strong>
          </div>
        </header>

        {!stats || stats.trial_count === 0 ? (
          <p className="empty">No benchmark data yet.</p>
        ) : (
          <div className="slide__grid">
            <MetricCharts models={stats.models} compact />
            <div className="slide__right">
              <MetricsTable models={stats.models} compact />
              <ol className="answers answers--slide">
                {stats.answers.map((a) => (
                  <li key={a.q}>
                    <strong>{a.q}</strong>
                    <span>{a.a}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        )}
        <footer className="slide__foot">
          {config.student_name} · {config.roll_number}
        </footer>
      </div>
    </section>
  );
}
