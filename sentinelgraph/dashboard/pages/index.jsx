/**
 * SentinelGraph investigation console.
 *
 * Three views of the same engine — Investigate (Track 1), Remember (Track 2),
 * Company Brain (Track 3) — plus a benchmark comparison panel.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Head from "next/head";
import { health, ingest, investigate, verify, commit, companyBrain, runEval, audit, graphStats } from "../lib/api";

const TENANT = "tenant_acme";

const PRINCIPAL = {
  id: "analyst_1",
  name: "Analyst 1",
  tenant_id: TENANT,
  roles: ["investigator", "verifier", "red_team"],
  cross_tenant: false,
};

export default function App() {
  const [tab, setTab] = useState("investigate");
  const [healthInfo, setHealth] = useState(null);
  const [healthErr, setHealthErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [bench, setBench] = useState(null);
  const [benchErr, setBenchErr] = useState(null);
  const txRef = useRef("txn_0");

  useEffect(() => {
    let alive = true;
    health().then(setHealth).catch((e) => setHealthErr(e.message));
    return () => { alive = false; };
  }, []);

  const runInvestigate = useCallback(async () => {
    setBusy(true); setError(null); setResult(null);
    try {
      const r = await investigate({
        transaction_id: txRef.current,
        tenant_id: TENANT,
        depth: 3,
        principal: PRINCIPAL,
      });
      setResult(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [txRef.current]);

  const runCompanyBrain = useCallback(async (incidentId) => {
    setBusy(true); setError(null); setResult(null);
    try {
      const r = await companyBrain({ incident_id: incidentId, tenant_id: TENANT, principal: PRINCIPAL });
      setResult({ kind: "company_brain", data: r });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, []);

  const runEvalBench = useCallback(async () => {
    setBusy(true); setBenchErr(null); setBench(null);
    try {
      const r = await runEval({ scale: "tiny", seed: 20261015, n_cases: 8 });
      setBench(r);
    } catch (e) {
      setBenchErr(e.message);
    } finally {
      setBusy(false);
    }
  }, []);

  const NAV = [
    { id: "investigate", label: "Investigate", group: "Track 1" },
    { id: "remember", label: "Remember", group: "Track 2" },
    { id: "company", label: "Company Brain", group: "Track 3" },
    { id: "bench", label: "Benchmark", group: "Validation" },
  ];

  return (
    <>
      <Head>
        <title>SentinelGraph — Trust-Aware Investigation & Memory Engine</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <div className="shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-name">
              SentinelGraph<em>·investigate</em>
            </div>
            <div className="brand-tag">Adversarially verified context graph</div>
          </div>
          <nav>
            {NAV.map((n) => (
              <button
                key={n.id}
                className={`nav-item ${tab === n.id ? "is-active" : ""}`}
                onClick={() => { setTab(n.id); setError(null); setResult(null); }}
              >
                <span className="nav-dot" />
                <span>{n.group}</span>
                <span style={{ marginLeft: "auto", fontSize: 11, color: "#6b7280" }}>{n.label}</span>
              </button>
            ))}
          </nav>
          <div className="sidebar-foot">
            <div className="tag">Backend</div>
            <div className="health" style={{ marginTop: 6 }}>
              <span className="dot" />
              {healthInfo ? `online · ${healthInfo.graph_backend}` : healthErr ? "offline" : "connecting…"}
            </div>
            <div className="tag">Tenant</div>
            <div className="mono kv" style={{ padding: "0 8px" }}>{TENANT}</div>
            <div className="tag">Claims are not facts</div>
            <div className="kv" style={{ padding: "0 8px", fontSize: 11 }}>{result ? result.verdict?.verdict || "—" : "—"}</div>
          </div>
        </aside>
        <main className="main">
          <div className="topbar">
            <div>
              <h1>{tabLabel(tab)}</h1>
              <div className="sub">{tabSub(tab)}</div>
            </div>
            <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
              <button className="btn" onClick={runEvalBench} disabled={busy}>
                {busy ? <span className="spinner" /> : "Run benchmark"}
              </button>
              <button className="btn primary" onClick={() => ingest({ scale: "tiny", seed: 20261015, principal: PRINCIPAL })} disabled={busy}>
                (Re)ingest world
              </button>
            </div>
          </div>

          {tab === "investigate" && (
            <InvestigationView run={runInvestigate} result={result} error={error} busy={busy} txRef={txRef} />
          )}
          {tab === "remember" && <MemoryView result={result} error={error} busy={busy} />}
          {tab === "company" && (
            <CompanyBrainView run={runCompanyBrain} result={result} error={error} busy={busy} />
          )}
          {tab === "bench" && <BenchView bench={bench} err={benchErr} busy={busy} run={runEvalBench} />}

          {error && <div className="card bad-msg" style={{ marginTop: 12 }}>{error}</div>}
        </main>
      </div>
    </>
  );
}

function tabLabel(t) {
  const L = { investigate: "Investigate (Track 1)", remember: "Remember (Track 2)", company: "Company Brain (Track 3)", bench: "Benchmark (Validation)" };
  return L[t] || t;
}
function tabSub(t) {
  const S = {
    investigate: "Multi-hop FalkorDB traversal → adversarial claim verification → governed memory update.",
    remember: "Versioned facts, corrections and structured handoffs persist across sessions.",
    company: "Incident → policy → owner/runbook, with backend-enforced access control.",
    bench: "Baseline A (retrieval) vs Baseline B (graph) vs SentinelGraph on shared cases.",
  };
  return S[t] || "";
}

function InvestigationView({ run, result, error, busy, txRef }) {
  const [txId, setTxId] = useState("txn_0");
  const [verdict, setVerdict] = useState(null);
  useEffect(() => {
    if (result && result.transaction_id) setVerdict(result.verdict);
  }, [result]);
  return (
    <div className="card">
      <div className="tag">1 · Connected evidence (FalkorDB)</div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12 }}>
        <input className="input" value={txId} onChange={(e) => setTxId(e.target.value)} placeholder="e.g. txn_0" />
        <button className="btn primary" onClick={() => { txRef.current = txId; run(); }} disabled={busy}>
          Investigate
        </button>
        {busy && <span className="spinner" style={{ marginLeft: 8 }} />}
      </div>
      {result && result.blue && (
        <>
          <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fill,minmax(200px,1fr))", marginBottom: 14 }}>
            <MetricCard label="Blue claims" value={result.blue.claims.length} />
            <MetricCard label="Red challenges" value={result.red.counterarguments.length} />
            <MetricCard label="Supported" value={result.verifier.claims.length} />
            <MetricCard label="Contradicted" value={result.verifier.counterarguments.length} />
          </div>
          <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fill,minmax(260px,1fr))", marginBottom: 14 }}>
            <Panel title="Blue Team — proposed claims" kind="claims" items={result.blue.claims} />
            <Panel title="Red Team — counterarguments" kind="counters" items={result.red.counterarguments} />
          </div>
          <Panel title="Verifier — evidence vs counterevidence" kind="verifier" items={result.verifier.claims} notes={result.verifier.notes} decision={result.verifier.decision} />
          <Panel title="Memory — controlled update" kind="memory" items={result.memory.claims} decision={result.memory.decision} notes={result.memory.notes} />
        </>
      )}
      {!result && !error && <div className="center">Enter a transaction id and run an investigation.</div>}
    </div>
  );
}

function MemoryView({ result, error, busy }) {
  return (
    <div className="card">
      <div className="tag">2 · Versioned memory & corrections</div>
      <p className="kv">Corrected facts are persisted as <span className="mono">MemoryVersion</span> / <span className="mono">Correction</span> nodes. A superseded claim never silently overwrites newer state.</p>
      {result && result.memory && (
        <div style={{ marginTop: 12 }}>
          <MetricCard label="Memory version" value={result.memory.decision.version} />
          <MetricCard label="Promoted" value={result.memory.decision.promoted} />
          <MetricCard label="Superseded" value={result.memory.decision.superseded} />
          <MetricCard label="Hypotheses retained" value={result.memory.decision.hypotheses_retained} />
          <div className="tag">Notes</div>
          <ul style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.6 }}>
            {result.memory.notes.map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      )}
      {!result && !error && <div className="center">Run an investigation first, then view its memory footprint.</div>}
    </div>
  );
}

function CompanyBrainView({ run, result, error, busy }) {
  const [incId, setIncId] = useState("inc_0");
  return (
    <div className="card">
      <div className="tag">3 · Organizational context with access control</div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12 }}>
        <input className="input" value={incId} onChange={(e) => setIncId(e.target.value)} placeholder="e.g. inc_0" />
        <button className="btn primary" onClick={() => run(incId)} disabled={busy}>Connect context</button>
        {busy && <span className="spinner" style={{ marginLeft: 8 }} />}
      </div>
      {result && result.kind === "company_brain" && (
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill,minmax(240px,1))" }}>
          <Panel title="Incident" items={result.data.incident ? [result.data.incident] : []} />
          <Panel title="Policy" items={result.data.policy || []} />
          <Panel title="Owner / team" items={result.data.owner ? [result.data.owner] : []} />
          <Panel title="Runbook" items={result.data.runbook || []} />
        </div>
      )}
      {!result && !error && <div className="center">Enter an incident id to connect incident → policy → owner → runbook.</div>}
    </div>
  );
}

function BenchView({ bench, err, busy, run }) {
  return (
    <div className="card">
      <div className="tag">Baseline comparison (same cases, same model)</div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12 }}>
        <button className="btn primary" onClick={run} disabled={busy}>
          {busy ? <span className="spinner" /> : "Run 3-baseline benchmark"}
        </button>
      </div>
      {err && <div className="bad-msg">{err}</div>}
      {bench && (
        <>
          <div style={{ display: "flex", gap: 14, marginBottom: 14 }}>
            <SummaryCard title="A · Retrieval" data={bench.baseline_a_retrieval} />
            <SummaryCard title="B · Graph" data={bench.baseline_b_graph} />
            <SummaryCard title="SentinelGraph" data={bench.sentinelgraph} accent="#60a5fa" />
          </div>
          <div className="tag">Per-scenario detail</div>
          <table>
            <thead><tr><th>Scenario</th><th>Kind</th><th>Truth</th><th>A pred</th><th>B pred</th><th>SG pred</th><th>A acc</th><th>B acc</th><th>SG acc</th></tr></thead>
            <tbody>
              {bench.details.a.map((r, i) => {
                const b = bench.details.b[i]; const s = bench.details.sg[i];
                return (
                  <tr key={r.scenario}>
                    <td>{r.scenario}</td><td>{r.kind}</td><td>{r.truth}</td>
                    <td>{aPred(r)}</td><td>{aPred(b)}</td><td>{aPred(s)}</td>
                    <td>{r.accuracy}</td><td>{b.accuracy}</td><td>{s.accuracy}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
      {!bench && !err && <div className="center">Run the benchmark to compare the three configurations.</div>}
    </div>
  );
}

function aPred(x) { return x ? x.prediction : "—"; }

function MetricCard({ label, value }) {
  return (
    <div style={{ background: "#0b0f19", border: "1px solid #1f2937", borderRadius: 8, padding: 10, textAlign: "center" }}>
      <div className="tag">{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: "#e5e7eb" }}>{value}</div>
    </div>
  );
}

function SummaryCard({ title, data, accent }) {
  return (
    <div style={{ background: "#0b0f19", border: `1px solid ${accent || "#374151"}`, borderRadius: 8, padding: 12, minWidth: 170 }}>
      <div className="tag" style={{ color: accent || "#9ca3af" }}>{title}</div>
      <div className="kv" style={{ fontSize: 12 }}><b>Accuracy</b> {data.accuracy}</div>
      <div className="kv" style={{ fontSize: 12 }}><b>Coverage</b> {data.evidence_coverage}</div>
      <div className="kv" style={{ fontSize: 12 }}><b>Claim support</b> {data.claim_support_rate}</div>
      <div className="kv" style={{ fontSize: 12 }}><b>Counter-evidence</b> {data.counterevidence_recall}</div>
      <div className="kv" style={{ fontSize: 12 }}><b>Disclosures</b> {data.unauthorized_disclosures}</div>
      <div className="kv" style={{ fontSize: 12 }}><b>Latency ms</b> {data.avg_latency_ms}</div>
    </div>
  );
}

function Panel({ title, kind, items, notes, decision }) {
  const empty = !items || items.length === 0;
  return (
    <div style={{ background: "#0b0f19", border: "1px solid #1f2937", borderRadius: 8, padding: 12, marginTop: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div className="tag">{title}</div>
        {!empty && <span className="badge info">{items.length}</span>}
      </div>
      {empty ? (
        <div className="center" style={{ padding: 10, fontSize: 12, color: "#6b7280" }}>—</div>
      ) : (
        <ul style={{ color: "#cbd5e1", fontSize: 12, lineHeight: 1.5, margin: 0, paddingLeft: 16 }}>
          {items.map((it, i) => {
            const txt = it.statement || it.title || it.description || JSON.stringify(it).slice(0, 120);
            return <li key={i}>{txt}</li>;
          })}
        </ul>
      )}
      {decision && (
        <div style={{ marginTop: 8, fontSize: 12, color: "#9ca3af" }}>
          <b>Decision:</b> {decision.verdict || JSON.stringify(decision).slice(0, 80)}
        </div>
      )}
      {notes && notes.length && (
        <div style={{ marginTop: 6, fontSize: 11, color: "#9ca3af" }}>
          {notes.map((n, i) => <div key={i}>· {n}</div>)}
        </div>
      )}
    </div>
  );
}
