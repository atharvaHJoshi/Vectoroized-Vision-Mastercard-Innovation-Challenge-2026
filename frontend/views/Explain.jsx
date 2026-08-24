import { useState } from "react";
import { post, pct, num, int, bandClass, money } from "../lib/api";
import { Card, ErrorNote, EmptyState, Badge, Skeleton, Table } from "../components/UI";
import { Gauge, Waterfall } from "../components/Charts";

export default function Explain({ run, simulate, busy }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [index, setIndex] = useState(0);

  const score = async (payload) => {
    if (!run || !run.run_id) return;
    setLoading(true);
    setError(null);
    try {
      setData(await post("/api/score", { run_id: run.run_id, ...payload }));
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  };

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
                <label>Or by row index</label>
                <input
                  type="number"
                  min="0"
                  value={index}
                  onChange={(ev) => setIndex(ev.target.value)}
                  style={{ width: 140 }}
                />
              </div>
              <button className="btn" onClick={() => score({ index: Number(index) })} disabled={loading}>
                Explain row
              </button>
            </div>
            <p style={{ fontSize: 12.5, color: "var(--text-faint)", marginTop: 10 }}>
              "Worst miss" finds the fraudulent transaction the model scored most
              confidently as legitimate — the most instructive failure to study.
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
                          <b style={{ color: t.fraud_label ? "var(--red)" : "var(--teal)" }}>
                            {t.fraud_label ? "FRAUD" : "LEGITIMATE"}
                          </b>
                        </div>
                        <div className="ba-row">
                          <span>Model was</span>
                          <b style={{ color: data.is_correct ? "var(--teal)" : "var(--red)" }}>
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
                subtitle={`Base value ${num(e.base_value, 4)}. Red bars pushed the score up, teal bars pushed it down. Rightmost column is the raw feature value.`}
              >
                <Waterfall
                  reasons={e.reasons}
                  protective={e.protective_factors}
                  emptyLabel="No material contributors"
                />
                <div className="legend" style={{ marginTop: 10 }}>
                  <span className="legend-item"><i style={{ background: "var(--red)" }} />risk-increasing</span>
                  <span className="legend-item"><i style={{ background: "var(--teal)" }} />protective</span>
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
                          <span style={{ color: "var(--teal)" }}>{num(r.contribution, 5)}</span>
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
