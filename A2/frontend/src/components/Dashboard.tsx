import type { Provider, StatsResponse } from "../api";
import { MetricCharts, MetricsTable } from "./metrics";

interface Props {
  stats: StatsResponse | null;
  testSet: string;
  onTestSet: (t: string) => void;
  testSets: string[];
  onRefresh: () => void;
  loading: boolean;
  scope: "all" | "latest";
  onScope: (s: "all" | "latest") => void;
  provider: Provider;
  onProvider: (p: Provider) => void;
}

export default function Dashboard({ stats, testSet, onTestSet, testSets, onRefresh, loading, scope, onScope, provider, onProvider }: Props) {
  return (
    <section className="dashboard">
      <div className="filters">
        <label>
          Models
          <select value={provider} onChange={(e) => onProvider(e.target.value as Provider)}>
            <option value="openrouter">OpenRouter (real experiment)</option>
            <option value="mock">Mock (simulated)</option>
          </select>
        </label>
        <label>
          Scope
          <select value={scope} onChange={(e) => onScope(e.target.value as "all" | "latest")}>
            <option value="all">All saved sessions</option>
            <option value="latest">Latest session only</option>
          </select>
        </label>
        <label>
          Test set
          <select value={testSet} onChange={(e) => onTestSet(e.target.value)}>
            {testSets.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <button className="btn btn--ghost" onClick={onRefresh} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
        {stats && (
          <span className="filters__meta">
            {stats.puzzle_count} puzzles × {stats.models.length} models = {stats.trial_count} trials ·{" "}
            {stats.sessions.length} session(s){` · ${stats.provider.toUpperCase()}`}
          </span>
        )}
      </div>

      {!stats || stats.trial_count === 0 ? (
        <p className="empty">No completed trials for this test set yet. Run a benchmark from the Race tab.</p>
      ) : (
        <>
          <MetricCharts models={stats.models} />
          <h3 className="section-title">All metrics</h3>
          <MetricsTable models={stats.models} />
          <h3 className="section-title">What the experiment answers</h3>
          <ol className="answers">
            {stats.answers.map((a) => (
              <li key={a.q}>
                <strong>{a.q}</strong>
                <span>{a.a}</span>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
