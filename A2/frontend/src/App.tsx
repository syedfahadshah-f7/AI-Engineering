import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, type AppConfig, type Budget, type Provider, type StatsResponse, type Sticker } from "./api";
import Dashboard from "./components/Dashboard";
import RacePanel from "./components/RacePanel";
import ResultsSlide from "./components/ResultsSlide";
import { PROVIDER_LABEL } from "./format";
import { initialRace, raceReducer } from "./race";

type Tab = "race" | "dashboard" | "slide";

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [stickers, setStickers] = useState<Sticker[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("race");
  const [race, dispatch] = useReducer(raceReducer, initialRace);

  const [testSet, setTestSet] = useState("three");
  const [count, setCount] = useState(1);
  const [startSeed, setStartSeed] = useState(1);
  const [actionError, setActionError] = useState<string | null>(null);

  const [statsSet, setStatsSet] = useState("three");
  const [statsProvider, setStatsProvider] = useState<Provider>("mock");
  const [budget, setBudget] = useState<Budget | null>(null);
  const [scope, setScope] = useState<"all" | "latest">("all");
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  useEffect(() => {
    Promise.all([api.config(), api.geometry()])
      .then(([c, g]) => {
        setConfig(c);
        setStatsProvider(c.provider);
        setStickers(g.stickers);
      })
      .catch((e) => setLoadError(String(e.message ?? e)));
  }, []);

  const modelKeys = config?.models.map((m) => m.key) ?? [];
  const running = race.sessionStatus === "running";
  const isOpenRouter = config?.provider === "openrouter";

  // Persistent API usage; refreshed while a session runs.
  useEffect(() => {
    if (!config) return;
    const load = () => api.budget().then(setBudget).catch(() => undefined);
    load();
    if (!running) return;
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, [config, running, race.finishedRaces]);

  // Preview the first puzzle when the suite/seed changes. Deliberately not
  // re-run when a session ends, so the final results stay on screen.
  const runningRef = useRef(running);
  runningRef.current = running;
  useEffect(() => {
    if (!config || runningRef.current) return;
    api
      .preview(testSet, startSeed)
      .then((p) => dispatch({ kind: "preview", puzzle: p, modelKeys: config.models.map((m) => m.key) }))
      .catch(() => undefined);
  }, [config, testSet, startSeed]);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      let sessions: string[] | undefined;
      if (scope === "latest") {
        const list = await api.sessions();
        const done = list.sessions
          .filter((s) => s.test_set === statsSet && s.provider === statsProvider)
          .sort((a, b) => b.created_at.localeCompare(a.created_at));
        sessions = done.length ? [done[0].id] : ["none"];
      }
      setStats(await api.stats(statsSet, statsProvider, sessions));
    } catch (e) {
      setStats(null);
      setActionError(String((e as Error).message));
    } finally {
      setStatsLoading(false);
    }
  }, [statsSet, scope, statsProvider]);

  useEffect(() => {
    if (tab !== "race") loadStats();
  }, [tab, loadStats]);

  // Refresh stats after every finished race so the dashboard stays current.
  useEffect(() => {
    if (race.finishedRaces > 0) loadStats();
  }, [race.finishedRaces, loadStats]);

  const start = async () => {
    setActionError(null);
    try {
      const session = await api.startSession({ test_set: testSet, count, start_seed: startSeed });
      dispatch({ kind: "reset", session, modelKeys });
      setStatsSet(testSet);
      setStatsProvider(config!.provider);
      api.events(session.id, (event) => dispatch({ kind: "event", event }), () => undefined);
    } catch (e) {
      setActionError(String((e as Error).message));
    }
  };

  const cancel = async () => {
    if (race.session) await api.cancel(race.session.id).catch(() => undefined);
  };

  if (loadError) {
    return (
      <div className="boot-error">
        <h1>Backend not reachable</h1>
        <p>{loadError}</p>
        <p>
          Start it with <code>uvicorn app.main:app --port 8000</code> inside <code>backend/</code>.
        </p>
      </div>
    );
  }
  if (!config) return <div className="boot">Loading…</div>;

  const puzzle = race.puzzle;
  const doneCount = Object.values(race.panels).filter((p) => p.status === "done").length;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand__cube" aria-hidden>
            ▦
          </span>
          <h1>RUBIK'S CUBE RACE</h1>
        </div>
        <nav className="tabs" aria-label="Views">
          {(["race", "dashboard", "slide"] as Tab[]).map((t) => (
            <button key={t} className={tab === t ? "is-active" : ""} onClick={() => setTab(t)}>
              {t === "race" ? "Race" : t === "dashboard" ? "Benchmark Dashboard" : "Results Slide"}
            </button>
          ))}
        </nav>
        <div className="identity" aria-label="Student identity">
          <span className="identity__name">{config.student_name}</span>
          <span className="identity__roll">{config.roll_number}</span>
        </div>
      </header>

      <div className={`provider-banner provider-banner--${config.provider}`} role="status">
        <span>Models: {PROVIDER_LABEL[config.provider]}</span>
        <span className="budget">
          Rules: start {testSet === "three" ? "exactly 3 moves" : testSet} from solved · max {config.rules.max_moves} moves
          {isOpenRouter && ` · ${config.models.find((m) => m.key === "llm")?.name} max ${config.models.find((m) => m.key === "llm")?.move_limit} moves`}
          {config.rules.cache_enabled ? " · persistent cache ON" : " · cache OFF"}
        </span>
        {budget && isOpenRouter && (
          <span className="budget">
            OpenRouter requests:{" "}
            <b className={budget.openrouter.total_calls >= budget.total_cap ? "over" : ""}>
              {budget.openrouter.total_calls}/{budget.total_cap}
            </b>
            {config.models.map((m) => (
              <span key={m.key}>
                {" · "}
                {m.name.split(" ")[0]} {budget.openrouter.models[m.model_id]?.calls ?? 0}/{m.call_cap}
              </span>
            ))}
            {" · "}cost <b>${budget.openrouter.cost_usd.toFixed(4)}</b>
          </span>
        )}
        {budget && <span className="budget">cache: {budget.cache.entries} responses, {budget.cache.total_hits} hits</span>}
      </div>

      {tab === "race" && (
        <main className="race">
          {!running && (
          <section className="controls">
            <label>
              Test set
              <select value={testSet} disabled={running} onChange={(e) => setTestSet(e.target.value)}>
                {Object.entries(config.test_sets).map(([k, v]) => (
                  <option key={k} value={k}>
                    {k} ({v.min}–{v.max} turns)
                  </option>
                ))}
              </select>
            </label>
            <label>
              Puzzles
              <input type="number" min={1} max={isOpenRouter ? config.openrouter_max_puzzles : 50} value={count}
                disabled={running || isOpenRouter}
                onChange={(e) => setCount(Math.max(1, Math.min(50, Number(e.target.value) || 1)))} />
            </label>
            <label>
              First seed
              <input type="number" min={0} value={startSeed} disabled={running}
                onChange={(e) => setStartSeed(Math.max(0, Number(e.target.value) || 0))} />
            </label>
            <button className="btn btn--primary" onClick={start}>
              ▶ Run benchmark
            </button>
            {actionError && <span className="error-text">{actionError}</span>}
          </section>
          )}

          {puzzle && (
            <section className="puzzle-bar">
              <span>
                <b>Puzzle</b> {race.raceTotal ? `${race.raceIndex + 1} / ${race.raceTotal}` : "preview"} · {puzzle.id}
              </span>
              <span>
                <b>Scramble</b> <code>{puzzle.scramble.join(" ")}</code> <em>(hidden from models)</em>
              </span>
              <span>
                <b>{puzzle.optimal_exact ? "Exact optimum" : "Upper bound"}</b> {puzzle.reference_moves} moves
              </span>
              <span>
                <b>Limit</b> {config.rules.max_moves} moves
              </span>
              <span className={`phase phase--${race.sessionStatus}`}>
                {running
                  ? doneCount === modelKeys.length
                    ? "Race complete"
                    : "In progress"
                  : race.sessionStatus === "idle"
                    ? "Ready"
                    : `Session ${race.sessionStatus}`}
              </span>
              {running && (
                <button className="btn btn--danger btn--small" onClick={cancel}>
                  ■ Stop
                </button>
              )}
            </section>
          )}
          {race.error && <div className="error-box">{race.error}</div>}

          <section className="grid">
            {config.models.map((spec) => (
              <RacePanel
                key={spec.key}
                spec={spec}
                panel={race.panels[spec.key] ?? { status: "idle", moves: [], invalid: [], result: null, startedAt: null, rank: null }}
                startState={puzzle?.state ?? config.solved_state}
                stickers={stickers}
                maxMoves={config.rules.max_moves}
                optimal={puzzle?.reference_moves ?? null}
              />
            ))}
          </section>
        </main>
      )}

      {tab === "dashboard" && (
        <main>
          <Dashboard
            stats={stats}
            testSet={statsSet}
            onTestSet={setStatsSet}
            testSets={Object.keys(config.test_sets)}
            onRefresh={loadStats}
            loading={statsLoading}
            provider={statsProvider}
            onProvider={setStatsProvider}
            scope={scope}
            onScope={setScope}
          />
        </main>
      )}

      {tab === "slide" && (
        <main>
          <ResultsSlide stats={stats} config={config} />
        </main>
      )}

      <footer className="id-footer">
        {config.student_name} · Roll No. {config.roll_number} · AI Engineering — Assignment 02
      </footer>
    </div>
  );
}
