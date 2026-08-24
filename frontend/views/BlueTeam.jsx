import { useCallback, useEffect, useState } from "react";
import { post, pct, num, int, shortAttack, recallColour } from "../lib/api";
import { Card, Kpi, ErrorNote, EmptyState, Skeleton, Table, Badge } from "../components/UI";
import { BarChart, LineChart } from "../components/Charts";

export default function BlueTeam({ run, simulate, busy, detect, setDetect }) {
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

  const m = (detect && detect.overall) || {};

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Blue Team Detection</h1>
        <p>
          Accuracy is deliberately not reported. At roughly 1% fraud prevalence a model
          that approves everything scores 99% accuracy and is worthless, so every figure
          here is a precision/recall quantity measured at a fixed false-positive budget.
        </p>
      </div>

      {!run || !run.run_id ? (
        <EmptyState
          title="No simulation loaded"
          body="Train a Blue Team detector by building a world first."
          action={
            <button className="btn btn-primary" onClick={() => simulate()} disabled={busy}>
              {busy ? "Building…" : "Run simulation"}
            </button>
          }
        />
      ) : (
        <>
          {error && <ErrorNote error={error} onRetry={load} />}

          <Card
            title="Detector performance on the held-out test window"
            subtitle={
              detect
                ? `Operating threshold ${num(detect.threshold, 5)}, chosen on the validation split at a ${pct(
                    detect.target_fpr,
                    1
                  )} false-positive budget. ${int(detect.n_scored)} transactions scored.`
                : "Scoring…"
            }
            tone="blue"
            actions={
              <button className="btn btn-ghost" onClick={load} disabled={loading}>
                {loading ? "Scoring…" : "Re-run detection"}
              </button>
            }
          >
            {loading || !detect ? (
              <Skeleton lines={4} />
            ) : (
              <>
                <div className="grid grid-4">
                  <Kpi label="Recall" value={pct(m.recall, 1)} tone="good" />
                  <Kpi label="Precision" value={pct(m.precision, 1)} tone="info" />
                  <Kpi label="F1" value={num(m.f1, 3)} />
                  <Kpi label="FPR" value={pct(m.fpr, 2)} tone="warn" />
                </div>
                <div className="grid grid-4" style={{ marginTop: 14 }}>
                  <Kpi label="ROC-AUC" value={num(m.roc_auc, 4)} />
                  <Kpi label="PR-AUC" value={num(m.pr_auc, 4)} />
                  <Kpi
                    label="Value caught"
                    value={pct(m.value_detected_share, 1)}
                    sub="share of fraudulent value stopped"
                  />
                  <Kpi
                    label="Scoring latency"
                    value={`${num(m.latency_us_per_txn, 1)} µs`}
                    sub="per transaction"
                  />
                </div>
                <div className="grid grid-4" style={{ marginTop: 14 }}>
                  <Kpi label="True positives" value={int(m.tp)} />
                  <Kpi label="False negatives" value={int(m.fn)} tone="bad" />
                  <Kpi label="False positives" value={int(m.fp)} />
                  <Kpi
                    label="Alerts / 1k good txns"
                    value={num(m.alerts_per_1k_legit, 1)}
                    sub="analyst workload proxy"
                  />
                </div>
              </>
            )}
          </Card>

          <div className="grid grid-2">
            <Card
              title="Recall by evasion skill"
              subtitle="The gradient that matters. HARD attacks deliberately mimic legitimate behaviour, so a large drop here is expected and is exactly what the adaptive loop targets."
            >
              <BarChart
                data={(detect?.by_difficulty || []).map((r) => ({
                  label: `${r.group} (n=${r.n})`,
                  value: r.recall,
                  colour:
                    r.recall >= 0.9 ? "var(--teal)" : r.recall >= 0.7 ? "var(--amber)" : "var(--red)",
                }))}
                format={(v) => pct(v, 1)}
                max={1}
                height={150}
                emptyLabel="Run detection to populate"
              />
            </Card>

            <Card
              title="Recall by attack family"
              subtitle="Sorted worst-first. These are the families where the defence needs work."
            >
              <BarChart
                data={(detect?.by_attack_type || []).map((r) => ({
                  label: `${shortAttack(r.group)} (${r.n})`,
                  value: r.recall,
                  colour:
                    r.recall >= 0.9 ? "var(--teal)" : r.recall >= 0.7 ? "var(--amber)" : "var(--red)",
                }))}
                format={(v) => pct(v, 1)}
                max={1}
                height={230}
                emptyLabel="Run detection to populate"
              />
            </Card>
          </div>

          <div className="grid grid-2">
            <Card
              title="Recall vs. false-positive budget"
              subtitle="Every point is a deployable operating point. Choosing one is a business decision about customer friction."
            >
              <LineChart
                series={[
                  {
                    name: "recall",
                    colour: "var(--teal)",
                    showDots: true,
                    points: (detect?.operating_curve || []).map((p) => [p.realised_fpr * 100, p.recall]),
                  },
                  {
                    name: "precision",
                    colour: "var(--blue)",
                    dashed: true,
                    showDots: true,
                    points: (detect?.operating_curve || []).map((p) => [p.realised_fpr * 100, p.precision]),
                  },
                ]}
                xLabel="false-positive rate (%)"
                xFormat={(v) => v.toFixed(1)}
                yFormat={(v) => v.toFixed(2)}
                emptyLabel="Run detection to populate"
              />
              <Table
                columns={[
                  { key: "fpr_budget", header: "Budget", render: (r) => pct(r.fpr_budget, 2) },
                  { key: "realised_fpr", header: "Realised", render: (r) => pct(r.realised_fpr, 3) },
                  { key: "recall", header: "Recall", align: "right", render: (r) => pct(r.recall, 1) },
                  { key: "precision", header: "Precision", align: "right", render: (r) => pct(r.precision, 1) },
                  {
                    key: "alerts_per_1k_legit",
                    header: "Alerts/1k",
                    align: "right",
                    render: (r) => num(r.alerts_per_1k_legit, 1),
                  },
                ]}
                rows={detect?.operating_curve || []}
                empty="Run detection to populate"
              />
            </Card>

            <Card
              title="What the model relies on"
              subtitle="Cover-weighted split importance. Note that no label-derived column can appear here — the feature contract forbids it."
            >
              <BarChart
                data={(detect?.top_features || []).slice(0, 14).map((f) => ({
                  label: f.label,
                  value: f.importance,
                  colour: "var(--blue)",
                }))}
                format={(v) => num(v, 4)}
                height={330}
                emptyLabel="Run detection to populate"
              />
            </Card>
          </div>

          <Card
            title="Customer friction"
            subtitle="The other half of the trade-off: how much honest traffic gets challenged in exchange for the recall above."
          >
            {detect?.friction ? (
              <div className="grid grid-4">
                <Kpi
                  label="Legit challenged"
                  value={pct(detect.friction.legit_challenged_share, 2)}
                  sub="step-up or hold on good payments"
                  tone={detect.friction.legit_challenged_share < 0.02 ? "good" : "warn"}
                />
                <Kpi
                  label="Fraud stopped"
                  value={pct(detect.friction.fraud_stopped_share, 1)}
                  sub="challenged or held"
                  tone="good"
                />
                <Kpi
                  label="Fraud allowed through"
                  value={pct(detect.friction.fraud_allowed_share, 1)}
                  tone="bad"
                />
                <Kpi
                  label="Legit allowed straight through"
                  value={pct(detect.friction.legit_allowed_share, 1)}
                  tone="info"
                />
              </div>
            ) : (
              <Skeleton lines={2} />
            )}
          </Card>
        </>
      )}
    </div>
  );
}
