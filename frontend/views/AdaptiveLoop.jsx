import { useEffect, useState } from "react";
import { get, runJob, pct, num, int, signed } from "../lib/api";
import { Card, Kpi, ErrorNote, EmptyState, ProgressLog, Table, Badge } from "../components/UI";
import { DeltaBar, BarChart } from "../components/Charts";

/**
 * The hero screen.
 *
 * The story it has to tell: the system found its own weakness, generated harder
 * attacks aimed at that weakness, retrained, and improved — measured on attacks
 * the retrained model never saw, at a matched false-positive budget.
 */
export default function AdaptiveLoop({ run, simulate, busy, loop, setLoop }) {
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState([]);
  const [error, setError] = useState(null);
  const [nAdv, setNAdv] = useState(200);
  const [rounds, setRounds] = useState(2);
  const [useSearch, setUseSearch] = useState(true);

  // Adopt a previously computed loop result if one exists.
  useEffect(() => {
    if (loop) return;
    let alive = true;
    get("/api/loop/latest")
      .then((r) => {
        if (alive && r && r.result) setLoop(r.result);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [loop, setLoop]);

  const start = async () => {
    if (!run || !run.run_id) return;
    setRunning(true);
    setError(null);
    setProgress([]);
    try {
      const res = await runJob(
        "/api/loop",
        {
          run_id: run.run_id,
          n_adversarial: Number(nAdv),
          search_rounds: Number(rounds),
          use_search: useSearch,
        },
        (m) => setProgress((p) => [...p, m]),
        2000
      );
      setLoop(res);
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  };

  const b = loop && loop.before;
  const a = loop && loop.after;
  const d = loop && loop.delta;
  const plan = loop && loop.adaptation_plan;
  const meta = loop && loop.meta;

  return (
    <div className="stack">
      <div className="hero">
        <h1>Adaptive Attack / Defence Loop</h1>
        <p className="hero-sub">
          The defence is diagnosed, the Red Team generates attacks aimed at the diagnosed
          weakness, the Blue Team retrains, and the result is measured on a fresh
          adversarial batch the retrained model has never seen — at the same
          false-positive budget as before. That last constraint is what makes the
          improvement real rather than a threshold trick.
        </p>
        {run && run.run_id && (
          <div className="controls" style={{ marginTop: 18 }}>
            <div className="field">
              <label>Adversarial scenarios</label>
              <input
                type="number"
                min="20"
                max="5000"
                value={nAdv}
                onChange={(e) => setNAdv(e.target.value)}
                style={{ width: 120 }}
              />
            </div>
            <div className="field">
              <label>Search rounds</label>
              <input
                type="number"
                min="1"
                max="6"
                value={rounds}
                onChange={(e) => setRounds(e.target.value)}
                style={{ width: 90 }}
              />
            </div>
            <div className="field">
              <label>Mode</label>
              <div className="chips">
                <button
                  className={`chip chip-blue ${useSearch ? "on" : ""}`}
                  onClick={() => setUseSearch(true)}
                >
                  score-guided search
                </button>
                <button
                  className={`chip chip-blue ${!useSearch ? "on" : ""}`}
                  onClick={() => setUseSearch(false)}
                >
                  interpretable only
                </button>
              </div>
            </div>
            <button className="btn btn-hero" onClick={start} disabled={running}>
              {running ? "Running loop…" : "Run adaptive loop"}
            </button>
          </div>
        )}
      </div>

      {!run || !run.run_id ? (
        <EmptyState
          title="No simulation loaded"
          body="The loop needs a world and a trained baseline detector to attack."
          action={
            <button className="btn btn-primary" onClick={() => simulate()} disabled={busy}>
              {busy ? "Building…" : "Run simulation"}
            </button>
          }
        />
      ) : null}

      {error && <ErrorNote error={error} onRetry={start} />}
      {(running || progress.length > 0) && (
        <ProgressLog lines={progress} running={running} title="Adaptive loop" />
      )}

      {loop && b && a && (
        <>
          <Card
            title="Result on the held-out adversarial batch"
            subtitle={meta ? meta.methodology : undefined}
            tone="amber"
          >
            <div className="ba">
              <div className="ba-side">
                <div className="ba-tag">Before — baseline defence</div>
                <div className="ba-metric">{pct(b.recall, 1)}</div>
                <div className="ba-rows">
                  <div className="ba-row"><span>Precision</span><b>{pct(b.precision, 1)}</b></div>
                  <div className="ba-row"><span>F1</span><b>{num(b.f1, 4)}</b></div>
                  <div className="ba-row"><span>PR-AUC</span><b>{num(b.pr_auc, 4)}</b></div>
                  <div className="ba-row"><span>Attacks missed</span><b>{int(b.fn)}</b></div>
                  <div className="ba-row"><span>False-positive rate</span><b>{pct(b.fpr, 3)}</b></div>
                </div>
              </div>

              <div className="ba-arrow">
                <div style={{ fontSize: 24 }}>→</div>
                <div className={`ba-delta ${d.recall_delta < 0 ? "neg" : ""}`}>
                  {signed(d.recall_delta, 3)}
                </div>
                <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em" }}>
                  recall
                </div>
              </div>

              <div className="ba-side after">
                <div className="ba-tag">After — hardened defence</div>
                <div className="ba-metric">{pct(a.recall, 1)}</div>
                <div className="ba-rows">
                  <div className="ba-row"><span>Precision</span><b>{pct(a.precision, 1)}</b></div>
                  <div className="ba-row"><span>F1</span><b>{num(a.f1, 4)}</b></div>
                  <div className="ba-row"><span>PR-AUC</span><b>{num(a.pr_auc, 4)}</b></div>
                  <div className="ba-row"><span>Attacks missed</span><b>{int(a.fn)}</b></div>
                  <div className="ba-row"><span>False-positive rate</span><b>{pct(a.fpr, 3)}</b></div>
                </div>
              </div>
            </div>

            <div className="matched-note">
              False-positive rate held at {pct(a.fpr, 3)} on both sides — the recall gain is
              not bought with extra customer friction.
            </div>
          </Card>

          <div className="grid grid-4">
            <Kpi label="Recall gain" value={signed(d.recall_delta, 3)} tone={d.recall_delta > 0 ? "good" : "bad"} big />
            <Kpi label="F1 gain" value={signed(d.f1_delta, 3)} tone={d.f1_delta > 0 ? "good" : "bad"} />
            <Kpi label="PR-AUC gain" value={signed(d.pr_auc_delta, 3)} tone={d.pr_auc_delta > 0 ? "good" : "bad"} />
            <Kpi
              label="Attacks now caught"
              value={int((d.missed_before || 0) - (d.missed_after || 0))}
              sub={`${int(d.missed_before)} → ${int(d.missed_after)} missed`}
              tone="good"
            />
          </div>

          <div className="grid grid-2">
            <Card title="Metric movement">
              <DeltaBar before={b.recall} after={a.recall} label="Recall" />
              <DeltaBar before={b.f1} after={a.f1} label="F1" format={(v) => num(v, 3)} />
              <DeltaBar before={b.pr_auc} after={a.pr_auc} label="PR-AUC" format={(v) => num(v, 3)} />
            </Card>

            <Card
              title="Regression check on the original attack distribution"
              subtitle="Hardening against new attacks must not degrade performance on the attacks the defence already handled. This is the guard against overfitting to the adversarial batch."
            >
              {loop.baseline_on_baseline && loop.hardened_on_baseline && (
                <>
                  <DeltaBar
                    before={loop.baseline_on_baseline.recall}
                    after={loop.hardened_on_baseline.recall}
                    label="Recall on baseline attacks"
                  />
                  <Table
                    columns={[
                      { key: "k", header: "Metric" },
                      { key: "before", header: "Baseline model", align: "right" },
                      { key: "after", header: "Hardened model", align: "right" },
                    ]}
                    rows={[
                      {
                        k: "Recall",
                        before: pct(loop.baseline_on_baseline.recall, 1),
                        after: pct(loop.hardened_on_baseline.recall, 1),
                      },
                      {
                        k: "Precision",
                        before: pct(loop.baseline_on_baseline.precision, 1),
                        after: pct(loop.hardened_on_baseline.precision, 1),
                      },
                      {
                        k: "F1",
                        before: num(loop.baseline_on_baseline.f1, 4),
                        after: num(loop.hardened_on_baseline.f1, 4),
                      },
                      {
                        k: "ROC-AUC",
                        before: num(loop.baseline_on_baseline.roc_auc, 4),
                        after: num(loop.hardened_on_baseline.roc_auc, 4),
                      },
                    ]}
                  />
                </>
              )}
            </Card>
          </div>

          <Card
            title="What the Red Team decided to do, and why"
            subtitle="Each move is an auditable knob change justified by a measured weakness — not an opaque search."
            tone="red"
          >
            {(plan?.moves || []).length === 0 ? (
              <p style={{ color: "var(--text-muted)" }}>
                No exploitable gap was identified — the defence had no trait that
                discriminated misses from catches.
              </p>
            ) : (
              (plan.moves || []).map((m, i) => (
                <div className="move" key={i}>
                  <div className="move-head">
                    <span className="move-cause">{m.cause_label}</span>
                    <span className="move-lift">lift {num(m.lift, 2)}×</span>
                    <Badge>{pct(m.share_of_missed, 0)} of misses</Badge>
                    <Badge>knob: {m.knob}</Badge>
                  </div>
                  <div className="move-body">{m.rationale}</div>
                </div>
              ))
            )}
            {plan?.target_segments?.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <div className="ba-tag">Generation concentrated on</div>
                <div className="chips">
                  {plan.target_segments.slice(0, 6).map((s, i) => (
                    <Badge key={i} className="sev-high">
                      {s.attack_type} / {s.difficulty} — {pct(s.recall, 0)} recall
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </Card>

          {loop.search_history?.length > 0 && (
            <Card
              title="Evasion search"
              subtitle="Black-box search: candidates are scored by the deployed detector and only the most evasive are kept — the same thing an attacker probing a live endpoint would do."
            >
              <Table
                columns={[
                  { key: "round", header: "Round" },
                  { key: "intensity", header: "Intensity", align: "right", render: (r) => num(r.intensity, 2) },
                  { key: "candidates", header: "Candidates", align: "right" },
                  { key: "kept", header: "Kept", align: "right" },
                  {
                    key: "mean_score_all",
                    header: "Mean score (all)",
                    align: "right",
                    render: (r) => num(r.mean_score_all, 5),
                  },
                  {
                    key: "mean_score_kept",
                    header: "Mean score (kept)",
                    align: "right",
                    render: (r) => (
                      <span style={{ color: "var(--red)" }}>{num(r.mean_score_kept, 5)}</span>
                    ),
                  },
                ]}
                rows={loop.search_history}
              />
            </Card>
          )}

          {meta && (
            <Card title="Run detail">
              <Table
                columns={[
                  { key: "k", header: "Property" },
                  { key: "v", header: "Value", render: (r) => <code>{r.v}</code> },
                ]}
                rows={[
                  ["Adversarial scenarios used for retraining", int(meta.adv_train_scenarios)],
                  ["Held-out adversarial scenarios (evaluation)", int(meta.adv_eval_scenarios)],
                  ["Held-out events evaluated", int(meta.eval_population?.n)],
                  ["  of which fraudulent", int(meta.eval_population?.n_fraud)],
                  ["False-positive budget", pct(meta.target_fpr, 2)],
                  ["Threshold before / after", `${num(meta.threshold_before, 5)} / ${num(meta.threshold_after, 5)}`],
                  ["Model", String(meta.model_kind).toUpperCase()],
                  ["Search enabled", meta.used_search ? "yes" : "no"],
                  ["Elapsed", `${num(meta.elapsed_seconds, 1)} s`],
                ].map(([k, v]) => ({ k, v: String(v) }))}
              />
            </Card>
          )}
        </>
      )}

      {!loop && !running && run && run.run_id && (
        <EmptyState
          title="Loop not yet run"
          body="Press “Run adaptive loop” above. At scale tiny this takes roughly one to three minutes: it diagnoses the deployed model, searches for evasive attacks against it, retrains, and re-measures on a held-out batch."
        />
      )}
    </div>
  );
}
