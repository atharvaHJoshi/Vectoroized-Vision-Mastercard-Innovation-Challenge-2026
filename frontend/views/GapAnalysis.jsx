import { useCallback, useEffect, useState } from "react";
import { get, post, pct, num, int, shortAttack, recallColour } from "../lib/api";
import { Card, Kpi, ErrorNote, EmptyState, Skeleton, Table, Badge } from "../components/UI";
import { BarChart } from "../components/Charts";

export default function GapAnalysis({ run, simulate, busy, gap, setGap, goto }) {
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!run || !run.run_id) return;
    setLoading(true);
    setError(null);
    try {
      setGap(await post("/api/gap", { run_id: run.run_id, on: "test" }));
    } catch (e) {
      // fall back to whatever the backend already stored
      try {
        const stored = await get("/api/gap");
        setGap(stored && stored.report ? { ...stored.report, headline: null } : null);
      } catch {
        setError(e);
      }
    } finally {
      setLoading(false);
    }
  }, [run, setGap]);

  useEffect(() => {
    if (run && run.run_id && !gap) load();
  }, [run, gap, load]);

  const causes = (gap && gap.causes) || [];
  const segments = (gap && gap.weakest_segments) || [];

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Gap Analysis</h1>
        <p>
          A benchmark reports a score. This asks the more useful question: of the attacks
          that got through, what did they have in common, and how much of the failure does
          each trait actually explain?
        </p>
      </div>

      {!run || !run.run_id ? (
        <EmptyState
          title="No simulation loaded"
          body="Gap analysis explains a specific detector's failures, so a trained detector is needed first."
          action={
            <button className="btn btn-primary" onClick={() => simulate()} disabled={busy}>
              {busy ? "Building…" : "Run simulation"}
            </button>
          }
        />
      ) : (
        <>
          {error && <ErrorNote error={error} onRetry={load} />}
          {loading && <Card><Skeleton lines={6} /></Card>}

          {gap && !loading && (
            <>
              {gap.headline && (
                <Card tone="amber">
                  <p style={{ margin: 0, fontSize: 14 }}>{gap.headline}</p>
                </Card>
              )}

              <div className="grid grid-4">
                <Kpi label="Attacks tested" value={int(gap.n_attacks)} />
                <Kpi label="Detected" value={int(gap.n_detected)} tone="good" />
                <Kpi label="Evaded detection" value={int(gap.n_missed)} tone="bad" big />
                <Kpi label="Recall" value={pct(gap.recall, 1)} />
              </div>

              <Card
                title="Attribution — how much of the failure each trait explains"
                subtitle="Attribution is derived from excess prevalence: how much more common a trait is among misses than among catches. A trait present in 90% of misses but also 90% of catches explains nothing, so it scores near zero."
              >
                <BarChart
                  data={causes
                    .filter((c) => c.attribution > 0)
                    .map((c) => ({
                      label: c.label,
                      value: c.attribution,
                      colour: "var(--amber)",
                    }))}
                  format={(v) => pct(v, 0)}
                  max={Math.max(...causes.map((c) => c.attribution || 0), 0.1)}
                  height={220}
                  emptyLabel="No misses to explain — recall is perfect on this population"
                />
              </Card>

              <Card title="Evasion traits in detail">
                <Table
                  columns={[
                    { key: "label", header: "Trait", width: "22%" },
                    {
                      key: "share_of_missed",
                      header: "% of misses",
                      align: "right",
                      render: (r) => pct(r.share_of_missed, 0),
                    },
                    {
                      key: "share_of_detected",
                      header: "% of catches",
                      align: "right",
                      render: (r) => pct(r.share_of_detected, 0),
                    },
                    {
                      key: "lift",
                      header: "Lift",
                      align: "right",
                      render: (r) => (
                        <span
                          style={{
                            color:
                              r.lift >= 2 ? "var(--red)" : r.lift >= 1.2 ? "var(--amber)" : "var(--text-muted)",
                            fontFamily: "var(--mono)",
                          }}
                        >
                          {num(r.lift, 2)}×
                        </span>
                      ),
                    },
                    {
                      key: "attribution",
                      header: "Attribution",
                      align: "right",
                      render: (r) => pct(r.attribution, 0),
                    },
                    {
                      key: "remediation",
                      header: "Recommended remediation",
                      width: "36%",
                      render: (r) => (
                        <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{r.remediation}</span>
                      ),
                    },
                  ]}
                  rows={causes}
                  rowKey={(r) => r.key}
                  empty="No misses to explain"
                />
              </Card>

              <div className="grid grid-2">
                <Card
                  title="Weakest segments"
                  subtitle="Attack family crossed with evasion skill, coloured by recall. This is the map of where the defence is thin."
                >
                  <Table
                    columns={[
                      { key: "attack_type", header: "Family", render: (r) => shortAttack(r.attack_type) },
                      { key: "difficulty", header: "Skill", render: (r) => <Badge>{r.difficulty}</Badge> },
                      { key: "n", header: "n", align: "right" },
                      { key: "missed", header: "Missed", align: "right" },
                      {
                        key: "recall",
                        header: "Recall",
                        align: "right",
                        cellStyle: (r) => ({ background: recallColour(r.recall), fontWeight: 600 }),
                        render: (r) => pct(r.recall, 0),
                      },
                    ]}
                    rows={segments}
                    rowKey={(r, i) => `${r.attack_type}-${r.difficulty}-${i}`}
                    empty="No segments with enough support"
                  />
                </Card>

                <Card title="By attack family" subtitle="Worst first.">
                  <BarChart
                    data={(gap.by_attack_type || []).map((r) => ({
                      label: `${shortAttack(r.group)} (${r.n})`,
                      value: r.recall,
                      colour:
                        r.recall >= 0.9 ? "var(--green)" : r.recall >= 0.7 ? "var(--amber)" : "var(--red)",
                    }))}
                    format={(v) => pct(v, 0)}
                    max={1}
                    height={230}
                    emptyLabel="No data"
                  />
                </Card>
              </div>

              <Card
                title="Worked examples — the most confident failures"
                subtitle="The fraudulent transactions the model was most certain were legitimate. Traits list which evasion hypotheses each one satisfies."
              >
                <Table
                  columns={[
                    { key: "attack_id", header: "Attack", render: (r) => <code>{r.attack_id}</code> },
                    { key: "attack_type", header: "Family", render: (r) => shortAttack(r.attack_type) },
                    { key: "difficulty", header: "Skill" },
                    { key: "attack_stage", header: "Stage", render: (r) => String(r.attack_stage).replace(/_/g, " ").toLowerCase() },
                    { key: "amount", header: "Amount", align: "right", render: (r) => `₹${int(r.amount)}` },
                    {
                      key: "amount_ratio_customer_median",
                      header: "× normal",
                      align: "right",
                      render: (r) => `${num(r.amount_ratio_customer_median, 2)}×`,
                    },
                    { key: "score", header: "Score", align: "right", render: (r) => num(r.score, 5) },
                    {
                      key: "traits",
                      header: "Traits",
                      render: (r) => (
                        <span style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {(r.traits || []).slice(0, 4).map((t) => (
                            <span className="sig" key={t}>{t.toLowerCase().replace(/_/g, " ")}</span>
                          ))}
                        </span>
                      ),
                    },
                  ]}
                  rows={gap.examples || []}
                  rowKey={(r) => r.transaction_id}
                  empty="No missed attacks"
                />
              </Card>

              <Card tone="amber" title="Next step">
                <p style={{ margin: "0 0 12px", color: "var(--text-muted)" }}>
                  The Red Team can now target these specific weaknesses and the Blue Team
                  can be retrained against the result.
                </p>
                <button className="btn btn-hero" onClick={() => goto("loop")}>
                  Run the adaptive loop →
                </button>
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}
