/**
 * Shared UI primitives: layout shell, cards, KPIs, tables, states.
 */
import { useEffect, useState } from "react";
import { get } from "../lib/api";

/* --------------------------------------------------------------- KPI card */
export function Kpi({ label, value, sub, tone, big }) {
  return (
    <div className={`kpi ${tone ? `kpi-${tone}` : ""} ${big ? "kpi-big" : ""}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

export function Card({ title, subtitle, children, actions, tone }) {
  return (
    <section className={`card ${tone ? `card-${tone}` : ""}`}>
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <p className="card-sub">{subtitle}</p>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}

/* ------------------------------------------------------------------ table */
export function Table({ columns, rows, empty = "No data", rowKey }) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return <div className="chart-empty">{empty}</div>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{ textAlign: c.align || "left", width: c.width }}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={rowKey ? rowKey(r, i) : i} style={r.__rowStyle}>
              {columns.map((c) => (
                <td key={c.key} style={{ textAlign: c.align || "left", ...(c.cellStyle ? c.cellStyle(r) : {}) }}>
                  {c.render ? c.render(r, i) : String(r[c.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ----------------------------------------------------------------- states */
export const Skeleton = ({ lines = 4, height = 18 }) => (
  <div className="skeleton-group">
    {Array.from({ length: lines }, (_, i) => (
      <div key={i} className="skeleton" style={{ height, width: `${100 - i * 7}%` }} />
    ))}
  </div>
);

export const ErrorNote = ({ error, onRetry }) => (
  <div className="note note-error">
    <strong>Something went wrong</strong>
    <p>{String(error && error.message ? error.message : error)}</p>
    {onRetry && (
      <button className="btn btn-ghost" onClick={onRetry}>
        Try again
      </button>
    )}
  </div>
);

export const EmptyState = ({ title, body, action }) => (
  <div className="note note-empty">
    <strong>{title}</strong>
    {body && <p>{body}</p>}
    {action}
  </div>
);

export const Badge = ({ children, className }) => (
  <span className={`badge ${className || ""}`}>{children}</span>
);

/* ---------------------------------------------------------- progress log */
export function ProgressLog({ lines, running, title = "Progress" }) {
  if (!lines || !lines.length) return null;
  return (
    <div className="log">
      <div className="log-head">
        {running && <span className="spinner" />}
        {title}
      </div>
      <ol>
        {lines.map((l, i) => (
          <li key={i}>{l}</li>
        ))}
      </ol>
    </div>
  );
}

/* ------------------------------------------------------------- run banner */
export function RunBanner({ run, onSimulate, busy }) {
  if (run && run.run_id) {
    const s = run.summary || {};
    return (
      <div className="runbar">
        <div>
          <span className="runbar-k">Active run</span>
          <code>{run.run_id}</code>
        </div>
        <div className="runbar-stats">
          <span>{(s.n_transactions || 0).toLocaleString("en-US")} transactions</span>
          <span>
            {s.fraud_prevalence !== undefined
              ? `${(s.fraud_prevalence * 100).toFixed(2)}% fraud`
              : ""}
          </span>
          <span>{s.n_attack_scenarios || 0} attack scenarios</span>
        </div>
        <button className="btn btn-ghost" onClick={onSimulate} disabled={busy}>
          {busy ? "Building…" : "New simulation"}
        </button>
      </div>
    );
  }
  return (
    <div className="runbar runbar-empty">
      <div>
        <strong>No simulation loaded.</strong> Build a synthetic payment world to
        begin.
      </div>
      <button className="btn btn-primary" onClick={onSimulate} disabled={busy}>
        {busy ? "Building…" : "Run simulation"}
      </button>
    </div>
  );
}

/* ------------------------------------------------------- backend presence */
export function useHealth() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let alive = true;
    get("/api/health")
      .then((h) => alive && setHealth(h))
      .catch((e) => alive && setError(e));
    return () => {
      alive = false;
    };
  }, []);
  return { health, error };
}
