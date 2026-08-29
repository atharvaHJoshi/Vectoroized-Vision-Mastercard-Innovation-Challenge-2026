import { useEffect, useState } from "react";
import { get, runJob, int, num, shortAttack } from "../lib/api";
import { Card, ErrorNote, EmptyState, Skeleton, Badge, Table, ProgressLog } from "../components/UI";
import { BarChart, EntropyBar } from "../components/Charts";

export default function RedTeam({ run, simulate, busy }) {
  const [cfg, setCfg] = useState(null);
  const [types, setTypes] = useState([]);
  const [difficulty, setDifficulty] = useState("HARD");
  const [n, setN] = useState(300);
  const [result, setResult] = useState(null);
  const [progress, setProgress] = useState([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    get("/api/config")
      .then((c) => {
        if (!alive) return;
        setCfg(c);
        setTypes(c.attack_types || []);
      })
      .catch((e) => alive && setError(e));
    return () => {
      alive = false;
    };
  }, []);

  const toggle = (t) =>
    setTypes((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));

  const generate = async () => {
    if (!run || !run.run_id) return;
    setRunning(true);
    setError(null);
    setProgress([]);
    try {
      // Generation + feature rebuild on a populated world runs ~40s, which
      // outlasts the Next dev proxy's 30s upstream cap for a single response.
      // The backend runs it as a job, so poll it and surface progress instead
      // of blocking on one long request.
      setResult(
        await runJob(
          "/api/redteam/generate",
          {
            run_id: run.run_id,
            n_scenarios: Number(n),
            attack_types: types.length ? types : null,
            difficulty,
          },
          (m) => setProgress((p) => [...p, m]),
          1500
        )
      );
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  };

  const d = result && result.diversity;

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Red Team Simulator</h1>
        <p>
          The Red Team does not replay fixed scripts. For every scenario it independently
          samples the attack family, evasion skill, victim persona, amounts, devices,
          geography, pacing and sequence length — so diversity is a measured property
          rather than a claim.
        </p>
      </div>

      {!run || !run.run_id ? (
        <EmptyState
          title="No simulation loaded"
          body="The Red Team attacks a specific synthetic population, so a world must exist first."
          action={
            <button className="btn btn-primary" onClick={() => simulate()} disabled={busy}>
              {busy ? "Building…" : "Run simulation"}
            </button>
          }
        />
      ) : (
        <>
          <Card title="Configure attack campaign" tone="red">
            {!cfg ? (
              <Skeleton lines={3} />
            ) : (
              <>
                <div className="field" style={{ marginBottom: 14 }}>
                  <label>Attack families ({types.length} selected)</label>
                  <div className="chips">
                    {(cfg.attack_types || []).map((t) => (
                      <button
                        key={t}
                        className={`chip ${types.includes(t) ? "on" : ""}`}
                        onClick={() => toggle(t)}
                      >
                        {shortAttack(t)}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="controls">
                  <div className="field">
                    <label>Evasion skill</label>
                    <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
                      {(cfg.difficulties || []).map((x) => (
                        <option key={x} value={x}>{x}</option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label>Scenarios</label>
                    <input
                      type="number"
                      min="1"
                      max="20000"
                      value={n}
                      onChange={(e) => setN(e.target.value)}
                      style={{ width: 120 }}
                    />
                  </div>
                  <button className="btn btn-red" onClick={generate} disabled={running}>
                    {running ? "Generating…" : "Generate attacks"}
                  </button>
                </div>

                {cfg.difficulty_descriptions && cfg.difficulty_descriptions[difficulty] && (
                  <p style={{ fontSize: 12.5, color: "var(--text-faint)", marginTop: 12 }}>
                    <strong style={{ color: "var(--text-muted)" }}>{difficulty}: </strong>
                    {cfg.difficulty_descriptions[difficulty]}
                  </p>
                )}
              </>
            )}
          </Card>

          {error && <ErrorNote error={error} onRetry={generate} />}

          {(running || progress.length > 0) && (
            <ProgressLog lines={progress} running={running} title="Red team generation" />
          )}

          {result && (
            <>
              <div className="grid grid-4">
                <div className="kpi kpi-bad">
                  <div className="kpi-label">Scenarios</div>
                  <div className="kpi-value">{int(result.n_scenarios)}</div>
                </div>
                <div className="kpi">
                  <div className="kpi-label">Events</div>
                  <div className="kpi-value">{int(result.n_events)}</div>
                  <div className="kpi-sub">{num(d?.events_per_scenario_mean, 1)} per scenario</div>
                </div>
                <div className="kpi">
                  <div className="kpi-label">Distinct victims</div>
                  <div className="kpi-value">{int(d?.distinct_victims)}</div>
                  <div className="kpi-sub">{int(d?.distinct_victim_personas)} personas</div>
                </div>
                <div className="kpi">
                  <div className="kpi-label">Amount span</div>
                  <div className="kpi-value">10^{num(d?.amount_span_log10, 1)}</div>
                  <div className="kpi-sub">
                    ₹{int(d?.amount_p05)} – ₹{int(d?.amount_p95)}
                  </div>
                </div>
              </div>

              <div className="grid grid-2">
                <Card
                  title="Measured diversity"
                  subtitle="Normalised entropy: 1.0 means perfectly even coverage of that dimension, 0 means everything collapsed onto one value."
                >
                  <EntropyBar label="Attack family" value={d?.entropy_attack_type} />
                  <EntropyBar label="Evasion skill" value={d?.entropy_difficulty} />
                  <EntropyBar label="Victim persona" value={d?.entropy_persona} />
                  <EntropyBar label="Geography" value={d?.entropy_city} />
                  <EntropyBar label="Attack stage" value={d?.entropy_stage} />
                  <div className="legend" style={{ marginTop: 12 }}>
                    <span className="legend-item">{int(d?.distinct_devices)} devices</span>
                    <span className="legend-item">{int(d?.distinct_cities)} cities</span>
                    <span className="legend-item">{int(d?.distinct_merchants)} merchants</span>
                    <span className="legend-item">{int(d?.distinct_stages)} stages</span>
                  </div>
                </Card>

                <Card title="Composition">
                  <BarChart
                    data={Object.entries(result.by_type || {}).map(([k, v]) => ({
                      label: shortAttack(k),
                      value: v,
                      colour: "var(--red)",
                    }))}
                    format={(v) => int(v)}
                    height={190}
                    emptyLabel="No scenarios"
                  />
                  <div style={{ marginTop: 14 }}>
                    <BarChart
                      data={Object.entries(result.by_difficulty || {}).map(([k, v]) => ({
                        label: k,
                        value: v,
                        colour: "var(--violet)",
                      }))}
                      format={(v) => int(v)}
                      height={120}
                      emptyLabel="No scenarios"
                    />
                  </div>
                </Card>
              </div>

              <Card title="Sample scenarios" subtitle="Each row is a multi-event attack sequence, not a single fake transaction.">
                <Table
                  columns={[
                    { key: "attack_id", header: "ID", render: (r) => <code>{r.attack_id}</code> },
                    { key: "attack_type", header: "Family", render: (r) => shortAttack(r.attack_type) },
                    { key: "difficulty", header: "Skill", render: (r) => <Badge>{r.difficulty}</Badge> },
                    { key: "persona", header: "Victim persona" },
                    { key: "n_events", header: "Events", align: "right" },
                    { key: "total_value", header: "Total value", align: "right", render: (r) => `₹${int(r.total_value)}` },
                    {
                      key: "span_seconds",
                      header: "Span",
                      align: "right",
                      render: (r) =>
                        r.span_seconds > 86400
                          ? `${(r.span_seconds / 86400).toFixed(1)} d`
                          : `${(r.span_seconds / 3600).toFixed(1)} h`,
                    },
                  ]}
                  rows={result.scenarios_sample || []}
                  rowKey={(r) => r.attack_id}
                  empty="No scenarios generated"
                />
              </Card>

              <Card title="Sample events" subtitle="These are spliced into the victim's real timeline; behavioural features are then recomputed over the merged stream.">
                <Table
                  columns={[
                    { key: "transaction_id", header: "Txn", render: (r) => <code>{r.transaction_id}</code> },
                    { key: "attack_stage", header: "Stage", render: (r) => String(r.attack_stage).replace(/_/g, " ").toLowerCase() },
                    { key: "amount", header: "Amount", align: "right", render: (r) => `₹${int(r.amount)}` },
                    { key: "payment_method", header: "Method" },
                    { key: "transaction_type", header: "Type" },
                    { key: "city", header: "City" },
                    { key: "difficulty", header: "Skill" },
                  ]}
                  rows={result.events_sample || []}
                  rowKey={(r) => r.transaction_id}
                  empty="No events generated"
                />
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}
