import { useEffect, useState } from "react";
import { get, severityClass } from "../lib/api";
import { Card, Badge, ErrorNote, Skeleton } from "../components/UI";
import { StagePipeline } from "../components/Charts";

export default function Intelligence() {
  const [tax, setTax] = useState(null);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState({});

  useEffect(() => {
    let alive = true;
    get("/api/taxonomy")
      .then((t) => alive && setTax(t))
      .catch((e) => alive && setError(e));
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <ErrorNote error={error} />;
  if (!tax) {
    return (
      <div className="stack">
        <div className="page-head">
          <h1>Attack Intelligence</h1>
        </div>
        <Card><Skeleton lines={8} /></Card>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Attack Intelligence</h1>
        <p>{tax.description}</p>
      </div>

      <Card title="Why generative AI changes the problem" tone="amber">
        <p style={{ margin: 0, color: "var(--text-dim)", fontSize: 13 }}>
          {tax.genai_amplification_note}
        </p>
      </Card>

      <div className="intel">
        {(tax.attacks || []).map((a) => {
          const isOpen = !!open[a.attack_type];
          return (
            <article className="intel-card" key={a.attack_type}>
              <div className="intel-top">
                <div>
                  <div className="intel-name">{a.attack_name}</div>
                  <div className="intel-family">
                    {a.family} · {a.n_stages} stages · prior{" "}
                    {Number(a.base_rate_prior).toFixed(2)}
                  </div>
                  <div className="intel-target">
                    <strong style={{ color: "var(--text-dim)" }}>Target: </strong>
                    {a.target}
                  </div>
                  <div className="surfaces">
                    {(a.payment_surfaces || []).map((s) => (
                      <Badge key={s}>{s}</Badge>
                    ))}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Badge className={severityClass(a.severity)}>{a.severity}</Badge>
                  <button
                    className="btn btn-ghost"
                    onClick={() => setOpen((o) => ({ ...o, [a.attack_type]: !isOpen }))}
                  >
                    {isOpen ? "Less" : "Detail"}
                  </button>
                </div>
              </div>

              <StagePipeline stages={a.stages} />

              <div className="intel-grid">
                <div className="intel-block">
                  <h3>Role of generative AI</h3>
                  <p style={{ margin: 0, fontSize: 12.5, color: "var(--text-dim)" }}>
                    {a.genai_role}
                  </p>
                </div>
                <div className="intel-block">
                  <h3>Signals a defender can use</h3>
                  <div className="sig-list">
                    {(a.expected_signals || []).map((s) => (
                      <span className="sig" key={s}>{s}</span>
                    ))}
                  </div>
                </div>
              </div>

              {isOpen && (
                <>
                  <div className="intel-grid">
                    <div className="intel-block">
                      <h3>Behavioural changes in the event stream</h3>
                      <ul>
                        {(a.behavioural_changes || []).map((b, i) => (
                          <li key={i}>{b}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="intel-block">
                      <h3>Mitigations</h3>
                      <ul>
                        {(a.mitigations || []).map((m, i) => (
                          <li key={i}>{m}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                  <div className="hard-note">
                    <b>What the hard variant looks like: </b>
                    {a.hard_variant_note}
                  </div>
                </>
              )}
            </article>
          );
        })}
      </div>

      <Card title="Difficulty levels" subtitle="Every attack family is generated at four levels of evasion skill.">
        <div className="grid grid-2">
          {Object.entries(tax.difficulty_levels || {}).map(([k, v]) => (
            <div key={k}>
              <Badge className={k === "ADVERSARIAL" ? "sev-critical" : k === "HARD" ? "sev-high" : "sev-low"}>
                {k}
              </Badge>
              <p style={{ fontSize: 12.5, color: "var(--text-dim)" }}>{v}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Cross-cutting patterns">
        {(tax.cross_cutting_patterns || []).map((c) => (
          <div key={c.name} style={{ marginBottom: 14 }}>
            <strong style={{ fontSize: 13 }}>{c.name.replace(/_/g, " ")}</strong>
            <p style={{ fontSize: 12.5, color: "var(--text-dim)", margin: "3px 0" }}>
              {c.description}
            </p>
            <p style={{ fontSize: 12.5, color: "var(--amber)", margin: 0 }}>
              Implication: {c.implication}
            </p>
          </div>
        ))}
      </Card>
    </div>
  );
}
