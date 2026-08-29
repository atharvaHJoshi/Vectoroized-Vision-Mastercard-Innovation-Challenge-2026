import { useEffect, useMemo, useState } from "react";
import { post, pct, int, money, shortAttack } from "../lib/api";
import { Card, EmptyState, ErrorNote, Badge, Skeleton, Table } from "../components/UI";
import { StagePipeline, AttackTimeline, StackedBar } from "../components/Charts";

const DIFF_CLASS = {
  EASY: "band-low",
  MEDIUM: "band-medium",
  HARD: "band-high",
  ADVERSARIAL: "band-critical",
};

function fmtSpan(s) {
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}

export default function Studio({ run, busy, simulate, detect, goto }) {
  const rid = run && run.run_id;
  const gen = useMemo(
    () => ((run && run.generation && run.generation.attacks) || []).filter(Boolean),
    [run]
  );
  const truncated = useMemo(
    () => Boolean(run && run.generation && run.generation.truncated),
    [run]
  );

  const [revealed, setRevealed] = useState(0);
  const [playing, setPlaying] = useState(false);

  const [att, setAtt] = useState(null);
  const [anat, setAnat] = useState(null);
  const [anatLoading, setAnatLoading] = useState(false);
  const [anatError, setAnatError] = useState(null);

  // Reset the replay whenever a new generation arrives.
  useEffect(() => {
    setRevealed(0);
  }, [run && run.run_id]);

  const step = Math.max(1, Math.ceil(gen.length / 60));
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      setRevealed((r) => {
        if (r >= gen.length) {
          setPlaying(false);
          return r;
        }
        return Math.min(gen.length, r + step);
      });
    }, 120);
    return () => clearInterval(id);
  }, [playing, gen.length, step]);

  const shown = gen.slice(0, revealed);
  const done = revealed >= gen.length && gen.length > 0;

  useEffect(() => {
    if (done && gen.length > 0 && !att) {
      loadAnat(gen[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done]);

  const loadAnat = async (a) => {
    if (!rid || !a) return;
    setAtt(a);
    setAnatLoading(true);
    setAnatError(null);
    setAnat(null);
    try {
      setAnat(await post("/api/attack", { run_id: rid, attack_id: a.attack_id }));
    } catch (e) {
      setAnatError(e);
    } finally {
      setAnatLoading(false);
    }
  };

  const [kpi, kpiSub] = useMemo(() => {
    let n = 0;
    let v = 0;
    const fam = {};
    shown.forEach((a) => {
      n += Number(a.n_events) || 0;
      v += Number(a.total_value) || 0;
      fam[a.attack_type] = (fam[a.attack_type] || 0) + 1;
    });
    const segments = Object.entries(fam)
      .sort((x, y) => y[1] - x[1])
      .map(([k, val]) => ({ label: shortAttack(k), value: val }));
    return [
      [
        { label: "Scenarios generated", value: int(revealed) },
        { label: "Events spliced", value: int(n) },
        { label: "Value at risk", value: money(v) },
        { label: "Parallel families", value: int(Object.keys(fam).length) },
      ],
      segments,
    ];
  }, [shown, revealed]);

  const atkTableRows = useMemo(() => {
    if (!anat) return [];
    return (anat.events || []).map((e) => ({
      key: e.transaction_id,
      txid: e.transaction_id,
      stage: e.attack_stage,
      amount: money(e.amount),
      method: `${e.payment_method} · ${e.channel}`,
      city: e.city,
      score: e.fraud_probability,
      detected: e.detected,
    }));
  }, [anat]);

  const segMix = useMemo(() => {
    if (!gen.length) return [];
    const m = {};
    gen.forEach((a) => {
      const k = a.difficulty;
      m[k] = (m[k] || 0) + 1;
    });
    return Object.entries(m)
      .sort((x, y) => y[1] - x[1])
      .map(([k, v]) => ({
        label: k,
        value: v,
        colour:
          k === "EASY"
            ? "#22c55e"
            : k === "MEDIUM"
              ? "#f59e0b"
              : k === "HARD"
                ? "#f97316"
                : "#ef4444",
      }));
  }, [gen]);

  return (
    <div className="page">
      <div className="page-head">
        <h1>Attack Studio</h1>
        <p>
          Watch how the red team builds each attack on its victim, then open a
          single transaction to see exactly how it was generated.
        </p>
      </div>

      {!rid && (
        <Card>
          <EmptyState
            title="No simulation loaded"
            body="Run a simulation first so there is a generation to replay."
            action={
              <button className="btn btn-primary" onClick={() => simulate()} disabled={busy}>
                {busy ? "Building…" : "Run simulation"}
              </button>
            }
          />
        </Card>
      )}

      {rid && (
        <>
          <Card
            title="Generation feed"
            subtitle={
              gen.length
                ? `${gen.length} attacks recorded${truncated ? ` (first 2000 shown)` : ""}`
                : "Ran on an older run without telemetry — re-simulate to capture it."
            }
            actions={
              <>
                {gen.length > 0 && (
                  <button className="btn btn-ghost" onClick={() => { setPlaying(false); }} disabled={!playing && !done}>
                    Pause
                  </button>
                )}
                {gen.length > 0 && (
                  <button className="btn btn-ghost" onClick={() => { setRevealed(0); setPlaying(true); }}>
                    {done ? "Replay feed" : "Play feed"}
                  </button>
                )}
              </>
            }
          >
            {!gen.length ? (
              <EmptyState
                title="Nothing to replay"
                body="This run has no per-attack telemetry. Trigger a new simulation (or use the Red Team Simulator board) and come back."
                action={
                  <button className="btn btn-primary" onClick={() => simulate()} disabled={busy}>
                    Run a new simulation
                  </button>
                }
              />
            ) : (
              <>
                <div className="kpi-row">
                  {kpi.map((k) => (
                    <div key={k.label} className="kpi-mini">
                      <div className="kpi-label">{k.label}</div>
                      <div className="kpi-value">{k.value}</div>
                    </div>
                  ))}
                </div>

                {playing && (
                  <div className="progress-track">
                    <div
                      className="progress-fill"
                      style={{ width: `${(revealed / gen.length) * 100}%` }}
                    />
                  </div>
                )}

                <div className="mix-row">
                  <div className="mix-chart">
                    <h3>Difficulty mix (full batch)</h3>
                    <StackedBar segments={segMix} emptyLabel="No scenarios yet" />
                  </div>
                  <div className="mix-legend">
                    {shown.length ? (
                      <>
                        <h3>Live family mix (revealed so far)</h3>
                        {kpiSub.length ? (
                          kpiSub.map((s) => (
                            <div key={s.label} className="legend-item">
                              <span className="swatch" style={{ background: "var(--accent)" }} />
                              {s.label} ×{s.value}
                            </div>
                          ))
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </>
                    ) : (
                      <span className="text-muted">Reveal attacks to see the live mix.</span>
                    )}
                  </div>
                </div>

                <div className="atk-grid">
                  {shown.map((a) => (
                    <button
                      key={a.attack_id}
                      className={`atk-card ${att && att.attack_id === a.attack_id ? "is-selected" : ""}`}
                      onClick={() => loadAnat(a)}
                    >
                      <div className="atk-head">
                        <strong>{shortAttack(a.attack_type)}</strong>
                        <Badge className={DIFF_CLASS[a.difficulty] || "band-low"}>
                          {a.difficulty}
                        </Badge>
                      </div>
                      <div className="atk-sub">
                        <span>{a.persona}</span>
                        <span>{a.n_events} events · {money(a.total_value)}</span>
                      </div>
                    </button>
                  ))}
                </div>
                {done && (
                  <div className="note">
                    {gen.length} attacks generated. Click any card to dissect its
                    anatomy.
                    <button className="btn btn-ghost btn-sm" onClick={() => goto("redteam")}>
                      Open red team board
                    </button>
                  </div>
                )}
              </>
            )}
          </Card>

          <Card
            title={att ? `Anatomy — ${shortAttack(att.attack_type)} · ${att.attack_id}` : "Attack anatomy"}
            subtitle={
              att
                ? `${att.difficulty} · ${fmtSpan(att.span_seconds)} · ${att.persona} victim`
                : "Select an attack from the feed to see how it was generated."
            }
          >
            {att && !anatLoading && (
              <div className="anat-select">
                <label>
                  jump to
                  <select
                    value={att.attack_id}
                    onChange={(e) => {
                      const a = gen.find((x) => x.attack_id === e.target.value);
                      if (a) loadAnat(a);
                    }}
                  >
                    {gen.map((a) => (
                      <option key={a.attack_id} value={a.attack_id}>
                        {shortAttack(a.attack_type)} · {a.difficulty} · {a.attack_id}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}

            {!att && (
              <EmptyState
                title="No attack selected"
                body="Press play on the feed above, then click a card to dissect it."
              />
            )}
            {att && !anatError && (
              <>
                <StagePipeline stages={(att.stages || "").split("|")} />
                <div className="anat-knobs">
                  {anatLoading ? (
                    <Skeleton lines={3} />
                  ) : anat ? (
                    <>
                      <div className="knob-chips">
                        {Object.entries(anat.knobs || {})
                          .filter(([k]) =>
                            /amount_mult|stay_under_p95|p_new|p_high|hosting|spread_days|gap_|p_probe|reuse|credential|biometric|round_amount/.test(k)
                          )
                          .map(([k, v]) => (
                            <span key={k} className="knob-chip">
                              {k.replace(/_/g, " ")} <b>{Array.isArray(v) ? v.map((x) => Number(x).toFixed(2)).join("–") : v}</b>
                            </span>
                          ))}
                      </div>
                      <div className="anat-fam">
                        <h3>
                          {anat.family && anat.family.attack_name
                            ? `Family playbook — ${anat.family.attack_name}`
                            : `Family playbook — ${shortAttack(att.attack_type)}`}
                        </h3>
                        {anat.family && (
                          <p>
                            {anat.family.target || ""}
                            {anat.family.target && anat.family.genai_role ? " · " : ""}
                            {anat.family.genai_role || ""}
                          </p>
                        )}
                        {anat.family && anat.family.expected_signals && (
                          <div className="signals">
                            {anat.family.expected_signals.map((s) => (
                              <Badge key={s} className="band-low">{s}</Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    </>
                  ) : null}
                </div>

                <h3 className="section-title">Victim timeline around the splice</h3>
                {anatLoading ? (
                  <Skeleton lines={4} />
                ) : anat ? (
                  <AttackTimeline
                    points={(anat.timeline || []).map((t) => ({
                      t: t.timestamp,
                      amount: t.amount,
                      kind: t.is_attack ? "attack" : "legit",
                      stage: t.attack_stage || "",
                    }))}
                    emptyLabel="No events in this window"
                  />
                ) : (
                  <span className="text-muted">Loading timeline…</span>
                )}

                <h3 className="section-title">Attack events on the victim</h3>
                {anatLoading ? (
                  <Skeleton lines={5} />
                ) : anat ? (
                  <Table
                    rowKey={(r) => r.key}
                    empty="No attack events found"
                    columns={[
                      { key: "txid", header: "Transaction", render: (r) => <code className="mono">{r.txid}</code> },
                      {
                        key: "stage",
                        header: "Stage",
                        render: (r) => String(r.stage).replace(/_/g, " ").toLowerCase(),
                      },
                      { key: "amount", header: "Amount", align: "right" },
                      { key: "method", header: "Method · Channel" },
                      { key: "city", header: "City" },
                      {
                        key: "score",
                        header: "Model",
                        align: "right",
                        render: (r) =>
                          r.score === null || r.score === undefined ? (
                            <span className="text-muted">—</span>
                          ) : (
                            <Badge className={r.detected ? "band-critical" : "band-low"}>
                              {r.detected ? "CAUGHT" : "MISSED"} {pct(r.score, 2)}
                            </Badge>
                          ),
                      },
                    ]}
                    rows={atkTableRows}
                  />
                ) : (
                  <span className="text-muted">Loading events…</span>
                )}
              </>
            )}
            {anatError && <ErrorNote error={anatError} onRetry={() => loadAnat(att)} />}
          </Card>
        </>
      )}
    </div>
  );
}