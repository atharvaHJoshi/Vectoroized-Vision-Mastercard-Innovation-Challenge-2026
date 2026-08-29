import { useCallback, useEffect, useMemo, useState } from "react";
import Head from "next/head";

// NOTE: globals.css is imported ONLY in pages/_app.jsx. Next.js rejects a
// global stylesheet imported from any other module with
// "Global CSS cannot be imported from files other than your Custom <App>".
import { get, runRealtime } from "../lib/api";
import { RunBanner, useHealth } from "../components/UI";

import Overview from "../views/Overview";
import Intelligence from "../views/Intelligence";
import RedTeam from "../views/RedTeam";
import Studio from "../views/Studio";
import Live from "../views/Live";
import BlueTeam from "../views/BlueTeam";
import Explain from "../views/Explain";
import GapAnalysis from "../views/GapAnalysis";
import AdaptiveLoop from "../views/AdaptiveLoop";

const NAV = [
  { id: "overview", label: "Overview", group: "Situation" },
  { id: "live", label: "Live Monitor", group: "Situation", tone: "cyan", live: true },
  { id: "intel", label: "Attack Intelligence", group: "Situation" },
  { id: "redteam", label: "Red Team Simulator", group: "Red Team", tone: "red" },
  { id: "studio", label: "Attack Studio", group: "Red Team", tone: "red" },
  { id: "blueteam", label: "Blue Team Detection", group: "Blue Team", tone: "blue" },
  { id: "explain", label: "Explainability", group: "Blue Team", tone: "blue" },
  { id: "gap", label: "Gap Analysis", group: "Adaptive", tone: "amber" },
  { id: "loop", label: "Adaptive Loop", group: "Adaptive", tone: "amber", hero: true },
];

export default function App() {
  const [page, setPage] = useState("overview");
  const { health, error: healthError } = useHealth();

  // Shared run state, lifted so every page sees the same simulation.
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState([]);
  const [simError, setSimError] = useState(null);
  const [scale, setScale] = useState("tiny");

  // Cross-page caches so switching tabs does not refetch expensive results.
  const [detect, setDetect] = useState(null);
  const [gap, setGap] = useState(null);
  const [loop, setLoop] = useState(null);
  // Live per-scenario generation telemetry, streamed over SSE while a
  // simulation builds. Becomes redundant once the run completes.
  const [genFeed, setGenFeed] = useState(null);

  const simulate = useCallback(
    async (opts) => {
      setBusy(true);
      setSimError(null);
      setProgress([]);
      setDetect(null);
      setGap(null);
      setGenFeed([]);
      runRealtime(
        "/api/simulate",
        { scale: (opts && opts.scale) || scale, train: true, ...(opts || {}) },
        {
          onProgress: (m) => setProgress((p) => [...p, m]),
          onGeneration: (a) => setGenFeed((prev) => (prev ? [...prev, a] : [a])),
          onDone: (result) => {
            setRun(result);
            setGenFeed(null);
            setBusy(false);
          },
          onError: (e) => {
            setSimError(e);
            setBusy(false);
          },
        }
      );
    },
    [scale]
  );

  // If the backend already has a warm run from a previous session, adopt it.
  useEffect(() => {
    let alive = true;
    get("/api/runs")
      .then((r) => {
        if (!alive || !r) return;
        // default_run is the newest warm world; in_memory keeps every world
        // this process built (oldest first), but its DB row may have been
        // cleared by a later persist=True simulate.
        const live = r.default_run || (r.in_memory || [])[0];
        if (live) {
          get(`/api/runs/${live}`)
            .then((rec) => {
              if (!alive || !rec) return;
              setRun({
                run_id: live,
                summary: rec.live_summary || rec.summary,
                adopted: true,
              });
            })
            .catch(() => {});
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const shared = useMemo(
    () => ({
      run,
      busy,
      simulate,
      health,
      detect,
      setDetect,
      gap,
      setGap,
      loop,
      setLoop,
      genFeed,
      goto: setPage,
    }),
    [run, busy, simulate, health, detect, gap, loop, genFeed]
  );

  const groups = useMemo(() => {
    const out = [];
    NAV.forEach((n) => {
      const g = out.find((x) => x.name === n.group);
      if (g) g.items.push(n);
      else out.push({ name: n.group, items: [n] });
    });
    return out;
  }, []);

  const Body = {
    overview: Overview,
    live: Live,
    intel: Intelligence,
    redteam: RedTeam,
    studio: Studio,
    blueteam: BlueTeam,
    explain: Explain,
    gap: GapAnalysis,
    loop: AdaptiveLoop,
  }[page];

  return (
    <>
      <Head>
        <title>SovereignGuard — AI Payment Defence Lab</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta
          name="description"
          content="AI Red Team / Blue Team payment-security laboratory"
        />
      </Head>

      <div className="shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark" aria-hidden="true">
              <span className="mc mc-l" />
              <span className="mc mc-r" />
            </div>
            <div>
              <div className="brand-name">
                SovereignGuard<em>·finsim</em>
              </div>
              <div className="brand-tag">AI payment defence lab</div>
            </div>
          </div>

          <nav>
            {groups.map((g) => (
              <div className="nav-group" key={g.name}>
                <div className="nav-group-name">{g.name}</div>
                {g.items.map((n) => (
                  <button
                    key={n.id}
                    className={`nav-item ${page === n.id ? "is-active" : ""} ${
                      n.tone ? `tone-${n.tone}` : ""
                    } ${n.hero ? "is-hero" : ""}`}
                    onClick={() => setPage(n.id)}
                  >
                    <span className="nav-dot" />
                    {n.label}
                    {n.hero && <span className="nav-hero-tag">hero</span>}
                    {n.live && busy && <span className="nav-hero-tag">live</span>}
                  </button>
                ))}
              </div>
            ))}
          </nav>

          <div className="sidebar-foot">
            <div className="loop-legend">
              identify → generate → attack → detect → explain → adapt → retest
            </div>
            {health ? (
              <div className="health ok">
                <span className="dot" /> backend online
                <div className="health-sub">{health.ml_backend}</div>
              </div>
            ) : healthError ? (
              <div className="health bad">
                <span className="dot" /> backend offline
                <div className="health-sub">run: python sg.py serve</div>
              </div>
            ) : (
              <div className="health">
                <span className="dot" /> connecting…
              </div>
            )}
          </div>
        </aside>

        <main className="main">
          <div className="topbar">
            <RunBanner run={run} onSimulate={() => simulate()} busy={busy} />
            <label className="scale-pick">
              scale
              <select
                value={scale}
                onChange={(e) => setScale(e.target.value)}
                disabled={busy}
              >
                {["tiny", "demo", "large"].map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {Body ? <Body {...shared} progress={progress} simError={simError} /> : null}
        </main>
      </div>
    </>
  );
}
