import { useEffect, useMemo, useState } from "react";
import { get, post, int, pct, money, shortAttack } from "../lib/api";
import { Card, EmptyState, Badge, Skeleton } from "../components/UI";
import { StackedBar } from "../components/Charts";

/**
 * Live Monitor — the fintech operations wall.
 *
 * Two realtime modalities, both backed by genuine data:
 *  - while a simulation builds, per-scenario generation telemetry streams in
 *    over SSE and slides through the feed as it happens;
 *  - at rest, the deck polls the run record every 4s and re-renders the real
 *    summary, so the wall behaves exactly like a production console that
 *    consumes a live payment feed (swap the poll for a Kafka consumer and the
 *    chrome below does not change).
 */
const DIFF_CLASS = {
  EASY: "band-low",
  MEDIUM: "band-medium",
  HARD: "band-high",
  ADVERSARIAL: "band-critical",
};

export default function Live({ run, busy, simulate, genFeed, detect, setDetect, goto }) {
  const rid = run && run.run_id;
  const [sync, setSync] = useState(null);
  const [lastSyncT, setLastSyncT] = useState(0);
  const [detError, setDetError] = useState(null);

  // Realtime sync: the run record reflects the live in-memory world.
  useEffect(() => {
    if (!rid) return;
    let alive = true;
    const tick = async () => {
      try {
        const rec = await get(`/api/runs/${rid}`);
        if (alive && rec) {
          setSync(rec.live_summary || rec.summary || null);
          setLastSyncT(Date.now());
        }
      } catch { /* surface nothing; the deck degrades to the cached summary */ }
    };
    tick();
    const id = setInterval(tick, 4000);
    return () => { alive = false; clearInterval(id); };
  }, [rid]);

  // Detect on demand so the deck can show the deployed detector and its alarm.
  useEffect(() => {
    if (!rid || detect || busy) return;
    let alive = true;
    post("/api/detect", { run_id: rid })
      .then((d) => alive && setDetect(d))
      .catch((e) => alive && setDetError(e));
    return () => { alive = false; };
  }, [rid, detect, busy, setDetect]);

  const liveNow = Boolean(busy && genFeed && genFeed.length);
  const feed = liveNow ? genFeed : ((run && run.generation && run.generation.attacks) || []);
  const shown = liveNow ? feed : feed.slice(-60).reverse();

  const s = sync || (run && run.summary) || {};
  const m = (detect && detect.overall) || {};

  const mix = useMemo(() => {
    if (!feed.length) return [];
    const c = {};
    feed.forEach((a) => { c[a.attack_type] = (c[a.attack_type] || 0) + 1; });
    return Object.entries(c)
      .sort((a, b) => b[1] - a[1])
      .map(([k, v]) => ({ label: shortAttack(k), value: v }));
  }, [feed]);

  const totals = useMemo(() => {
    let events = 0;
    let value = 0;
    feed.forEach((a) => {
      events += Number(a.n_events) || 0;
      value += Number(a.total_value) || 0;
    });
    return { events, value };
  }, [feed]);

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Live Monitor</h1>
        <p>
          Real-time operations wall. Attack generation streams over
          Server-Sent Events the instant each scenario is built; at rest the
          deck syncs the world every few seconds exactly like a production
          payment-fraud console.
        </p>
      </div>

      {!rid && (
        <Card>
          <EmptyState
            title="No portfolio monitored"
            body="Start a simulation — the feed below becomes live as it builds."
            action={
              <button className="btn btn-primary" onClick={() => simulate()}>
                {busy ? "Building…" : "Run simulation"}
              </button>
            }
          />
        </Card>
      )}

      {rid && (
        <>
          <div className="live-head">
            {liveNow ? (
              <span className="live-bar"><span className="pulse-dot red" /> Generating attacks</span>
            ) : (
              <span className="live-bar paused"><span className="pulse-dot amber" /> Monitoring · sync {lastSyncT ? "just now" : "—"}</span>
            )}
            {detect && (
              <span className="live-bar">
                <span className="pulse-dot" />
                Detector armed · threshold {pct(detect.threshold, 4)}
              </span>
            )}
          </div>

          <div className="grid grid-4">
            <div className="stat-tick">
              <span className="st-label">Portfolio volume</span>
              <span className="st-value">{int(s.n_transactions)}</span>
              <span className="st-sub">{s.window_days || "—"} day window · {int(s.n_customers)} customers</span>
            </div>
            <div className="stat-tick">
              <span className="st-label">Fraud rate</span>
              <span className="st-value" style={{ color: "var(--mc-red)" }}>{pct(s.fraud_prevalence, 3)}</span>
              <span className="st-sub">{int(s.n_fraud_events)} labelled fraud events</span>
            </div>
            <div className="stat-tick">
              <span className="st-label">Attacks generated</span>
              <span className="st-value">{liveNow ? int(feed.length) : int(s.n_attack_scenarios)}</span>
              <span className="st-sub">{totals.events} events spliced · {money(totals.value)} at risk</span>
            </div>
            <div className="stat-tick">
              <span className="st-label">Attacker mix</span>
              <span className="st-value">{feed.length ? Object.keys(mix).length : "—"}</span>
              <span className="st-sub">{dedupFamilies(feed)} distinct families</span>
            </div>
          </div>

          <div className="grid grid-2">
            <Card
              title={liveNow ? "Live attacker feed" : "Latest attacker feed"}
              subtitle={
                liveNow
                  ? "Streamed from the generator as each scenario is built."
                  : "Replay of the generation recorded on this run."
              }
              actions={
                feed.length > 0 && (
                  <Badge className="band-high">{feed.length} scenarios</Badge>
                )
              }
            >
              {!feed.length ? (
                <EmptyState title="No activity yet" body="The feed fills as attacks generate." />
              ) : (
                <div className="feed">
                  {shown.map((a) => (
                    <div className="feed-row" key={`${a.attack_id}-${liveNow}`}>
                      <span className="feed-icon">{a.attack_type.slice(0, 2)}</span>
                      <span className="feed-main">
                        <div className="feed-title">{shortAttack(a.attack_type)}</div>
                        <div className="feed-meta">
                          {a.persona} · {a.n_events} events · {a.stages}
                        </div>
                      </span>
                      <span className="feed-right">
                        <Badge className={DIFF_CLASS[a.difficulty] || "band-low"}>{a.difficulty}</Badge>
                        <div className="feed-meta" style={{ marginTop: 3 }}>{money(a.total_value)}</div>
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card
              title="Portfolio posture"
              subtitle="Family distribution across everything the red team has thrown at this portfolio."
            >
              {detError && <p style={{ color: "var(--mc-red)" }}>Detection unavailable — {detError.message}</p>}
              {!feed.length ? (
                <EmptyState title="Nothing generated yet" body="Run a simulation or generate attacks from the Red Team board." />
              ) : (
                <>
                  <StackedBar segments={mix} emptyLabel="No families yet" height={52} />
                  <h3 className="section-title">Deployed detector</h3>
                  {!detect ? (
                    <Skeleton lines={2} />
                  ) : (
                    <div className="stat-rows">
                      <div className="stat-row">
                        <span>Recall on test window</span>
                        <b style={{ color: "var(--green)" }}>{pct(m.recall, 1)}</b>
                      </div>
                      <div className="stat-row">
                        <span>Precision</span>
                        <b>{pct(m.precision, 1)}</b>
                      </div>
                      <div className="stat-row">
                        <span>Alerts per 1,000 good txns</span>
                        <b>{Number(m.alerts_per_1k_legit || 0).toFixed(1)}</b>
                      </div>
                      <div className="stat-row">
                        <span>Attacks still breaking through</span>
                        <b style={{ color: m.fn > 0 ? "var(--mc-red)" : "var(--green)" }}>{int(m.fn)}</b>
                      </div>
                    </div>
                  )}
                </>
              )}
            </Card>
          </div>

          {feed.length > 0 && (
            <div className="note">
              Dig into any attack — how it was generated, stage by stage, on its
              victim.
              <button className="btn btn-ghost btn-sm" onClick={() => goto("studio")}>
                Open Attack Studio →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function dedupFamilies(feed) {
  return new Set(feed.map((a) => a.attack_type)).size;
}