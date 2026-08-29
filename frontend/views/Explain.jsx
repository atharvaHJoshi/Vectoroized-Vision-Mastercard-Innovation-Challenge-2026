import { useEffect, useState } from "react";
import { post, pct, num, int, bandClass, money, shortAttack } from "../lib/api";
import { Card, ErrorNote, EmptyState, Badge, Skeleton, Table } from "../components/UI";
import { Gauge, Waterfall } from "../components/Charts";

const DIFFS = ["EASY", "MEDIUM", "HARD", "ADVERSARIAL"];

export default function Explain({ run, simulate, busy }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [index, setIndex] = useState(0);
  const [txid, setTxid] = useState("");

  // attack search
  const [q, setQ] = useState("");
  const [family, setFamily] = useState("");
  const [diff, setDiff] = useState("");
  const [result, setResult] = useState("any");
  const [fraudOnly, setFraudOnly] = useState(true);
  const [rows, setRows] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [scen, setScen] = useState([]);
  const [chosen, setChosen] = useState("");

  const rid = run && run.run_id;

  // Load the generated attack scenarios once per run so the picker is warm.
  useEffect(() => {
    if (!rid) return;
    let alive = true;
    setChosen("");
    setRows(null);
    post("/api/attacks", { run_id: rid, limit: 1000 })
      .then((r) => alive && setScen(r.rows || []))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [rid]);

  const score = async (payload) => {
    if (!rid) return;
    setLoading(true);
    setError(null);
    try {
      setData(await post("/api/score", { run_id: rid, ...payload }));
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  };

  const search = async (payload) => {
    if (!rid) return;
    setSearchLoading(true);
    setSearchError(null);
    try {
      const body = { run_id: rid, diff, family, q, result, fraud_only: fraudOnly, limit: 200, ...payload };
      if (!body.family) delete body.family;
      if (!body.diff) delete body.diff;
      if (!body.q) delete body.q;
      setRows(await post("/api/search", body));
    } catch (e) {
      setSearchError(e);
    } finally {
      setSearchLoading(false);
    }
  };

  const families = (run && run.summary && run.summary.attack_types) || [];
  const t = data && data.transaction;
  const d = data && data.decision;
  const e = data && data.explanation;

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Explainability</h1>
        <p>
          Attributions come from a path-dependent TreeSHAP implementation written for this
          project and verified against a brute-force evaluation of the Shapley definition.
          The contributions below sum exactly to the model's output for this transaction.
        </p>
      </div>

      {!run || !run.run_id ? (
        <EmptyState
          title="No simulation loaded"
          body="Score a transaction from a built world to see why the model decided what it did."
          action={
            <button className="btn btn-primary" onClick={() => simulate()} disabled={busy}>
              {busy ? "Building…" : "Run simulation"}
            </button>
          }
        />
      ) : (
        <>
          <Card
            title="Find generated attacks"
            subtitle="Search the run's transaction stream by attack, family, or id — then score any event to explain its decision."
            tone="blue"
          >
            <div className="controls">
              <div className="field">
                <label>Attack scenario</label>
                <select value={chosen} onChange={(ev) => {
                  setChosen(ev.target.value);
                  search(ev.target.value ? { attack_id: ev.target.value } : {});
                }} style={{ minWidth: 280 }}>
                  <option value="">All scenarios</option>
                  {(scen || []).map((s) => (
                    <option key={s.attack_id} value={s.attack_id}>
                      {s.attack_id} · {shortAttack(s.attack_type)} / {s.difficulty} · {int(s.n_events)} ev · ₹{int(s.total_value)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Family</label>
                <select value={family} onChange={(ev) => setFamily(ev.target.value)}>
                  <option value="">All</option>
                  {families.map((f) => (
                    <option key={f} value={f}>{shortAttack(f)}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Skill</label>
                <select value={diff} onChange={(ev) => setDiff(ev.target.value)}>
                  <option value="">Any</option>
                  {DIFFS.map((l) => (
                    <option key={l} value={l}>{l}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Detection</label>
                <select value={result} onChange={(ev) => setResult(ev.target.value)}>
                  <option value="any">Any</option>
                  <option value="missed">Missed</option>
                  <option value="caught">Caught</option>
                </select>
              </div>
              <div className="field">
                <label>Search</label>
                <input
                  type="text"
                  value={q}
                  onChange={(ev) => setQ(ev.target.value)}
                  onKeyDown={(ev) => ev.key === "Enter" && search({})}
                  placeholder="tx / attack / customer id…"
                  style={{ width: 180 }}
                />
              </div>
              <label style={{ display: "flex", gap: 6, alignItems: "center", paddingBottom: 2 }}>
                <input type="checkbox" checked={fraudOnly} onChange={(ev) => setFraudOnly(ev.target.checked)} />
                Fraud only
              </label>
              <button className="btn btn-primary" onClick={() => search({})} disabled={searchLoading}>
                {searchLoading ? "Searching…" : "Find"}
              </button>
            </div>

            {searchError && <ErrorNote error={searchError} />}
            {searchLoading && <Skeleton lines={3} />}
            {rows && !searchLoading && (
              <>
                <p style={{ fontSize: 12.5, color: "var(--text-faint)", marginTop: 10 }}>
                  {int(rows.total)} matching transaction{rows.total === 1 ? "" : "s"}
                  {rows.scored ? ` · scored by the loaded detector (threshold ${num(rows.threshold, 4)})` : " · no detector loaded, so scores are unavailable"}
                  {" · click “Explain” on a row to see why the model decided what it did"}
                </p>
                <Table
                  columns={[
                    { key: "attack_id", header: "Attack", render: (r) => <code>{r.attack_id}</code> },
                    { key: "transaction_id", header: "Txn", render: (r) => <code>{r.transaction_id}</code> },
                    { key: "attack_type", header: "Family", render: (r) => shortAttack(r.attack_type) },
                    { key: "attack_stage", header: "Stage", render: (r) => String(r.attack_stage).replace(/_/g, " ").toLowerCase() },
                    { key: "difficulty", header: "Skill", render: (r) => <Badge>{r.difficulty}</Badge> },
                    { key: "amount", header: "Amount", align: "right", render: (r) => money(r.amount) },
                    { key: "city", header: "City" },
                    {
                      key: "fraud_probability",
                      header: "Score",
                      align: "right",
                      render: (r) =>
                        r.fraud_probability === undefined ? "—" : (
                          <span style={{ color: r.detected ? "var(--green)" : "var(--red)" }}>
                            {num(r.fraud_probability, 4)}
                          </span>
                        ),
                    },
                    {
                      key: "detected",
                      header: "",
                      render: (r) =>
                        r.detected === undefined ? null : (
                          <Badge className={r.detected ? "band-low" : "band-critical"}>
                            {r.detected ? "CAUGHT" : "MISSED"}
                          </Badge>
                        ),
                    },
                    {
                      key: "_explain",
                      header: "",
                      render: (r) => (
                        <button className="btn btn-ghost" onClick={() => score({ index: r.row_index })}>
                          Explain
                        </button>
                      ),
                    },
                  ]}
                  rows={rows.rows}
                  rowKey={(r) => r.transaction_id}
                  empty={searchError ? "" : "No matching transactions"}
                />
              </>
            )}
          </Card>

          <Card title="Pick a transaction to explain" tone="blue">
            <div className="controls">
              <button
                className="btn btn-primary"
                onClick={() => score({ worst_missed: true })}
                disabled={loading}
              >
                {loading ? "Scoring…" : "Explain the worst miss"}
              </button>
              <div className="field">
                <label>Transaction id</label>
                <input
                  type="text"
                  value={txid}
                  onChange={(ev) => setTxid(ev.target.value)}
                  placeholder="txn_…"
                  style={{ width: 180 }}
                />
              </div>
              <div className="field">
                <label>Or by row index</label>
                <input
                  type="number"
                  min="0"
                  value={index}
                  onChange={(ev) => setIndex(ev.target.value)}
                  style={{ width: 140 }}
                />
              </div>
              <button
                className="btn"
                onClick={() => score(txid.trim() ? { transaction_id: txid.trim() } : { index: Number(index) })}
                disabled={loading}
              >
                Explain
              </button>
            </div>
            <p style={{ fontSize: 12.5, color: "var(--text-faint)", marginTop: 10 }}>
              "Worst miss" finds the fraudulent transaction the model scored most
              confidently as legitimate — the most instructive failure to study.
              The row index is the positional row in the world's chronological
              transaction stream; use the search above to find the index of a
              generated attack instead of guessing.
            </p>
          </Card>

          {error && <ErrorNote error={error} />}
          {loading && <Card><Skeleton lines={6} /></Card>}

          {data && !loading && (
            <>
              <div className="grid grid-2">
                <Card title="Risk decision">
                  <div style={{ display: "flex", gap: 20, alignItems: "center", flexWrap: "wrap" }}>
                    <Gauge value={d.risk_score} band={d.risk_band} label="risk score / 100" />
                    <div style={{ flex: 1, minWidth: 200 }}>
                      <div className="ba-rows">
                        <div className="ba-row">
                          <span>Action</span>
                          <b>{String(d.action).replace(/_/g, " ")}</b>
                        </div>
                        <div className="ba-row">
                          <span>Model probability</span>
                          <b>{num(d.fraud_probability, 5)}</b>
                        </div>
                        <div className="ba-row">
                          <span>Band</span>
                          <b><Badge className={bandClass(d.risk_band)}>{d.risk_band}</Badge></b>
                        </div>
                        <div className="ba-row">
                          <span>Ground truth</span>
                          <b style={{ color: t.fraud_label ? "var(--red)" : "var(--green)" }}>
                            {t.fraud_label ? "FRAUD" : "LEGITIMATE"}
                          </b>
                        </div>
                        <div className="ba-row">
                          <span>Model was</span>
                          <b style={{ color: data.is_correct ? "var(--green)" : "var(--red)" }}>
                            {data.is_correct ? "correct" : "wrong"}
                          </b>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="note note-method" style={{ marginTop: 14 }}>
                    {data.narrative}
                  </div>
                </Card>

                <Card title="Transaction">
                  <Table
                    columns={[
                      { key: "k", header: "Field" },
                      { key: "v", header: "Value", render: (r) => <code>{r.v}</code> },
                    ]}
                    rows={[
                      ["Transaction", t.transaction_id],
                      ["Attack", t.attack_id || "—"],
                      ["Customer", t.customer_id],
                      ["Merchant", t.merchant_id],
                      ["Amount", money(t.amount)],
                      ["Method", `${t.payment_method} / ${t.channel}`],
                      ["Type", t.transaction_type],
                      ["City", t.city],
                      ["Auth", t.auth_result],
                      ["Attack family", t.attack_type === "NONE" ? "—" : t.attack_type],
                      ["Attack stage", t.attack_stage || "—"],
                      ["Evasion skill", t.difficulty || "—"],
                    ].map(([k, v]) => ({ k, v: String(v) }))}
                  />
                </Card>
              </div>

              <Card
                title="Why — SHAP contributions"
                subtitle={`Base value ${num(e.base_value, 4)} is the model's prior in log-odds. Red bars pushed the score toward fraud, teal bars pushed it away; bar length is the magnitude of each contribution and the rightmost column is the raw feature value.`}
              >
                <Waterfall
                  reasons={e.reasons}
                  protective={e.protective_factors}
                  baseValue={e.base_value}
                  prediction={e.fraud_probability}
                  emptyLabel="No material contributors"
                />
                <div className="legend" style={{ marginTop: 10 }}>
                  <span className="legend-item"><i style={{ background: "var(--red)" }} />risk-increasing</span>
                  <span className="legend-item"><i style={{ background: "var(--cyan)" }} />protective</span>
                </div>
              </Card>

              <div className="grid grid-2">
                <Card title="Risk drivers" subtitle="What the analyst would act on.">
                  <Table
                    columns={[
                      { key: "label", header: "Factor" },
                      { key: "value", header: "Value", align: "right", render: (r) => num(r.value, 3) },
                      {
                        key: "contribution",
                        header: "Contribution",
                        align: "right",
                        render: (r) => (
                          <span style={{ color: "var(--red)" }}>+{num(r.contribution, 5)}</span>
                        ),
                      },
                    ]}
                    rows={e.reasons || []}
                    empty="No risk-increasing factors"
                  />
                </Card>
                <Card title="Protective factors" subtitle="What argued for approving it — often the reason a hard attack succeeds.">
                  <Table
                    columns={[
                      { key: "label", header: "Factor" },
                      { key: "value", header: "Value", align: "right", render: (r) => num(r.value, 3) },
                      {
                        key: "contribution",
                        header: "Contribution",
                        align: "right",
                        render: (r) => (
                          <span style={{ color: "var(--cyan)" }}>{num(r.contribution, 5)}</span>
                        ),
                      },
                    ]}
                    rows={e.protective_factors || []}
                    empty="No protective factors"
                  />
                </Card>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}