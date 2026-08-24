import { useCallback, useEffect, useState } from "react";
import { post, pct, num, int, bandClass } from "../lib/api";
import { Card, Kpi, ErrorNote, Skeleton, EmptyState, ProgressLog, Badge } from "../components/UI";
import { StackedBar, LineChart } from "../components/Charts";

const BAND_COLOUR = {
  LOW: "#2dd4bf",
  MEDIUM: "#fbbf24",
  HIGH: "#fb923c",
  CRITICAL: "#f2555a",
};

export default function Overview({ run, busy, simulate, detect, setDetect, progress, simError, goto }) {
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!run || !run.run_id) return;
    setLoading(true);
    setError(null);
    try {
      setDetect(await post("/api/detect", { run_id: run.run_id }));
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [run, setDetect]);

  useEffect(() => {
    if (run && run.run_id && !detect) load();
  }, [run, detect, load]);

  const s = (run && run.summary) || {};
  const m = (detect && detect.overall) || {};

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Situation Overview</h1>
        <p>
          A synthetic payment portfolio is attacked by an AI Red Team and defended by an
          AI Blue Team. Every figure below is measured on a held-out test window at a
          fixed false-positive budget — never on data the model trained on.
        </p>
      </div>

      {simError && <ErrorNote error={simError} onRetry={() => simulate()} />}
      {busy && <ProgressLog lines={progress} running title="Building world" />}

      {!run || !run.run_id ? (
        !busy && (
          <EmptyState
            title="No simulation loaded"
            body="Build a synthetic payment world with customers, merchants, legitimate traffic and injected fraud, then train the baseline detector."
            action={
              <button className="btn btn-primary" onClick={() => simulate()}>
                Run simulation
              </button>
            }
          />
        )
      ) : (
        <>
          <div className="grid grid-4">
            <Kpi
              label="Detection rate (recall)"
              value={pct(m.recall, 1)}
              sub={`${int(m.tp)} of ${int(m.n_positive)} fraud events caught`}
              tone={m.recall >= 0.8 ? "good" : m.recall >= 0.6 ? "warn" : "bad"}
              big
            />
            <Kpi
              label="Precision"
              value={pct(m.precision, 1)}
              sub={`${int(m.fp)} false alarms`}
              tone="info"
            />
            <Kpi label="F1 score" value={num(m.f1, 3)} sub={`ROC-AUC ${num(m.roc_auc, 3)}`} />
            <Kpi
              label="False-positive rate"
              value={pct(m.fpr, 2)}
              sub={`${num(m.alerts_per_1k_legit, 1)} alerts / 1,000 good txns`}
              tone={m.fpr <= 0.012 ? "good" : "warn"}
            />
          </div>

          <div className="grid grid-4">
            <Kpi label="Transactions" value={int(s.n_transactions)} sub={`${s.window_days || "—"} day window`} />
            <Kpi label="Fraud prevalence" value={pct(s.fraud_prevalence, 2)} sub={`${int(s.n_fraud_events)} fraud events`} />
            <Kpi label="Attack scenarios" value={int(s.n_attack_scenarios)} sub={`${(s.attack_types || []).length} families`} />
            <Kpi label="Missed attacks" value={int(m.fn)} sub="analysed on the Gap page" tone="bad" />
          </div>

          {error && <ErrorNote error={error} onRetry={load} />}

          <div className="grid grid-2">
            <Card
              title="Risk-band distribution"
              subtitle="Where the policy engine routes traffic. A good operating point keeps almost all legitimate payments in ALLOW while pushing fraud into step-up or hold."
            >
              {loading ? (
                <Skeleton lines={3} />
              ) : (
                <>
                  <StackedBar
                    segments={(detect?.risk_distribution || []).map((b) => ({
                      label: b.band,
                      value: b.count,
                      colour: BAND_COLOUR[b.band] || "#3c4a68",
                    }))}
                    emptyLabel="Run detection to populate"
                  />
                  <div className="table-wrap" style={{ marginTop: 12 }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Band</th>
                          <th>Action</th>
                          <th style={{ textAlign: "right" }}>Fraud</th>
                          <th style={{ textAlign: "right" }}>Legit</th>
                          <th style={{ textAlign: "right" }}>% of all fraud</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(detect?.risk_distribution || []).map((b) => (
                          <tr key={b.band}>
                            <td><Badge className={bandClass(b.band)}>{b.band}</Badge></td>
                            <td style={{ color: "var(--text-dim)" }}>
                              {String(b.action || "").replace(/_/g, " ").toLowerCase()}
                            </td>
                            <td style={{ textAlign: "right" }}>{int(b.fraud)}</td>
                            <td style={{ textAlign: "right" }}>{int(b.legit)}</td>
                            <td style={{ textAlign: "right" }}>{pct(b.share_of_all_fraud, 1)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </Card>

            <Card
              title="Operating curve"
              subtitle="Recall attainable at each false-positive budget. The budget is a business constraint, so recall is maximised inside it rather than traded against it."
            >
              {loading ? (
                <Skeleton lines={5} />
              ) : (
                <LineChart
                  series={[
                    {
                      name: "recall",
                      colour: "var(--teal)",
                      showDots: true,
                      points: (detect?.operating_curve || []).map((p) => [
                        p.realised_fpr * 100,
                        p.recall,
                      ]),
                    },
                    {
                      name: "precision",
                      colour: "var(--blue)",
                      dashed: true,
                      showDots: true,
                      points: (detect?.operating_curve || []).map((p) => [
                        p.realised_fpr * 100,
                        p.precision,
                      ]),
                    },
                  ]}
                  xLabel="false-positive rate (%)"
                  yLabel="rate"
                  xFormat={(v) => `${v.toFixed(1)}`}
                  yFormat={(v) => v.toFixed(2)}
                  emptyLabel="Run detection to populate"
                />
              )}
            </Card>
          </div>

          <Card
            title="Where to go next"
            subtitle="The point of this lab is not the score above — it is what happens when the defence is attacked by something it has not seen."
          >
            <div className="grid grid-3">
              <button className="btn" onClick={() => goto("redteam")}>
                Generate new attacks →
              </button>
              <button className="btn" onClick={() => goto("gap")}>
                See why attacks got through →
              </button>
              <button className="btn btn-red" onClick={() => goto("loop")}>
                Run the adaptive loop →
              </button>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
