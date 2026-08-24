/**
 * Charts, hand-drawn as SVG.
 *
 * Deliberately dependency-free: no recharts, no chart.js, no d3. Every chart is
 * a small pure function of its data returning SVG. That keeps the dependency
 * surface at three packages (next, react, react-dom) and means there is no
 * chart library version to go wrong.
 *
 * All components degrade to an empty-state note rather than throwing when data
 * is missing or malformed.
 */
import { num, pct } from "../lib/api";

const EMPTY = (label) => (
  <div className="chart-empty">{label || "No data"}</div>
);

const safe = (rows) => (Array.isArray(rows) ? rows.filter(Boolean) : []);

/* ------------------------------------------------------------------ bars */
export function BarChart({
  data,
  height = 240,
  format = (v) => num(v, 3),
  colour = "var(--blue)",
  max,
  emptyLabel,
}) {
  const rows = safe(data);
  if (!rows.length) return EMPTY(emptyLabel);
  const hi = max ?? Math.max(...rows.map((d) => Number(d.value) || 0), 1e-9);
  const barH = 26;
  const gap = 8;
  const h = Math.max(height, rows.length * (barH + gap) + 10);
  const labelW = 190;

  return (
    <svg className="chart" viewBox={`0 0 700 ${h}`} preserveAspectRatio="xMinYMin meet">
      {rows.map((d, i) => {
        const v = Number(d.value) || 0;
        const w = Math.max(2, (v / hi) * (700 - labelW - 78));
        const y = i * (barH + gap) + 4;
        return (
          <g key={`${d.label}-${i}`}>
            <text x={labelW - 10} y={y + barH / 2 + 4} className="ax-label" textAnchor="end">
              {String(d.label).slice(0, 30)}
            </text>
            <rect x={labelW} y={y} width={w} height={barH} rx="3"
                  fill={d.colour || colour} />
            <text x={labelW + w + 8} y={y + barH / 2 + 4} className="ax-value">
              {format(v)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* ----------------------------------------------------- stacked band chart */
export function StackedBar({ segments, height = 44, emptyLabel }) {
  const rows = safe(segments).filter((s) => Number(s.value) > 0);
  if (!rows.length) return EMPTY(emptyLabel);
  const total = rows.reduce((a, s) => a + Number(s.value), 0) || 1;
  let x = 0;
  return (
    <div>
      <svg className="chart" viewBox={`0 0 700 ${height}`} preserveAspectRatio="none"
           style={{ height }}>
        {rows.map((s, i) => {
          const w = (Number(s.value) / total) * 700;
          const el = (
            <rect key={i} x={x} y={0} width={Math.max(w, 1)} height={height}
                  fill={s.colour} />
          );
          x += w;
          return el;
        })}
      </svg>
      <div className="legend">
        {rows.map((s, i) => (
          <span key={i} className="legend-item">
            <i style={{ background: s.colour }} />
            {s.label} · {pct(Number(s.value) / total, 1)}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ lines */
export function LineChart({
  series,
  xLabel = "",
  yLabel = "",
  height = 260,
  xFormat = (v) => String(v),
  yFormat = (v) => num(v, 2),
  emptyLabel,
}) {
  const all = safe(series).filter((s) => safe(s.points).length > 1);
  if (!all.length) return EMPTY(emptyLabel);

  const W = 700;
  const H = height;
  const pad = { l: 58, r: 16, t: 14, b: 42 };
  const xs = all.flatMap((s) => s.points.map((p) => p[0]));
  const ys = all.flatMap((s) => s.points.map((p) => p[1]));
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const y0 = 0;
  const y1 = Math.max(...ys, 1e-9);
  const sx = (v) => pad.l + ((v - x0) / (x1 - x0 || 1)) * (W - pad.l - pad.r);
  const sy = (v) => H - pad.b - ((v - y0) / (y1 - y0 || 1)) * (H - pad.t - pad.b);

  const ticks = 4;
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMinYMin meet">
      {Array.from({ length: ticks + 1 }, (_, i) => {
        const v = y0 + ((y1 - y0) * i) / ticks;
        return (
          <g key={i}>
            <line x1={pad.l} x2={W - pad.r} y1={sy(v)} y2={sy(v)} className="grid" />
            <text x={pad.l - 8} y={sy(v) + 4} className="ax-tick" textAnchor="end">
              {yFormat(v)}
            </text>
          </g>
        );
      })}
      {Array.from({ length: ticks + 1 }, (_, i) => {
        const v = x0 + ((x1 - x0) * i) / ticks;
        return (
          <text key={i} x={sx(v)} y={H - pad.b + 18} className="ax-tick" textAnchor="middle">
            {xFormat(v)}
          </text>
        );
      })}
      {all.map((s, si) => (
        <g key={si}>
          <polyline
            className="series"
            points={s.points.map((p) => `${sx(p[0])},${sy(p[1])}`).join(" ")}
            stroke={s.colour || "var(--blue)"}
            strokeDasharray={s.dashed ? "5 4" : undefined}
          />
          {s.showDots &&
            s.points.map((p, pi) => (
              <circle key={pi} cx={sx(p[0])} cy={sy(p[1])} r="3.5"
                      fill={s.colour || "var(--blue)"} />
            ))}
        </g>
      ))}
      {xLabel && (
        <text x={(W + pad.l) / 2} y={H - 6} className="ax-axis" textAnchor="middle">
          {xLabel}
        </text>
      )}
      {yLabel && (
        <text x={14} y={pad.t + 4} className="ax-axis">
          {yLabel}
        </text>
      )}
      {all.length > 1 && (
        <g>
          {all.map((s, i) => (
            <g key={i} transform={`translate(${W - pad.r - 150},${pad.t + i * 16})`}>
              <rect width="10" height="10" y="-8" fill={s.colour || "var(--blue)"} rx="2" />
              <text x="16" y="1" className="ax-tick">{s.name}</text>
            </g>
          ))}
        </g>
      )}
    </svg>
  );
}

/* ------------------------------------------------------------- risk gauge */
export function Gauge({ value, max = 100, label, band }) {
  const v = Math.max(0, Math.min(Number(value) || 0, max));
  const frac = v / max;
  const R = 78;
  const CX = 100;
  const CY = 96;
  const start = Math.PI;
  const end = 0;
  const a = start + (end - start) * frac;
  const px = CX + R * Math.cos(a);
  const py = CY + R * Math.sin(a) * -1;

  const arc = (from, to, colour, w = 14) => {
    const a0 = start + (end - start) * from;
    const a1 = start + (end - start) * to;
    const x0 = CX + R * Math.cos(a0);
    const y0 = CY - R * Math.sin(a0);
    const x1 = CX + R * Math.cos(a1);
    const y1 = CY - R * Math.sin(a1);
    return (
      <path d={`M ${x0} ${y0} A ${R} ${R} 0 0 1 ${x1} ${y1}`} stroke={colour}
            strokeWidth={w} fill="none" strokeLinecap="butt" />
    );
  };

  return (
    <svg viewBox="0 0 200 120" className="gauge">
      {arc(0, 0.3, "rgba(45,212,191,0.35)")}
      {arc(0.3, 0.6, "rgba(250,204,21,0.35)")}
      {arc(0.6, 0.8, "rgba(251,146,60,0.4)")}
      {arc(0.8, 1, "rgba(248,113,113,0.45)")}
      <line x1={CX} y1={CY} x2={px} y2={py} stroke="var(--text)" strokeWidth="3"
            strokeLinecap="round" />
      <circle cx={CX} cy={CY} r="5" fill="var(--text)" />
      <text x={CX} y={CY - 22} className="gauge-value" textAnchor="middle">
        {v.toFixed(1)}
      </text>
      {band && (
        <text x={CX} y={CY + 18} className="gauge-band" textAnchor="middle">
          {band}
        </text>
      )}
      {label && (
        <text x={CX} y={116} className="ax-tick" textAnchor="middle">
          {label}
        </text>
      )}
    </svg>
  );
}

/* --------------------------------------------------------- SHAP waterfall */
export function Waterfall({ reasons, protective, height = 300, emptyLabel }) {
  const pos = safe(reasons).map((r) => ({ ...r, sign: 1 }));
  const neg = safe(protective).map((r) => ({ ...r, sign: -1 }));
  const rows = [...pos, ...neg];
  if (!rows.length) return EMPTY(emptyLabel);

  const hi = Math.max(...rows.map((r) => Math.abs(Number(r.contribution) || 0)), 1e-9);
  const barH = 24;
  const gap = 9;
  const h = Math.max(height, rows.length * (barH + gap) + 16);
  const mid = 430;
  const span = 210;

  return (
    <svg className="chart" viewBox={`0 0 700 ${h}`} preserveAspectRatio="xMinYMin meet">
      <line x1={mid} x2={mid} y1={0} y2={h} className="grid" />
      {rows.map((r, i) => {
        const c = Number(r.contribution) || 0;
        const w = Math.max(2, (Math.abs(c) / hi) * span);
        const y = i * (barH + gap) + 6;
        const up = c > 0;
        return (
          <g key={i}>
            <text x={mid - span - 14} y={y + barH / 2 + 4} className="ax-label"
                  textAnchor="start">
              {String(r.label || r.feature).slice(0, 40)}
            </text>
            <rect x={up ? mid : mid - w} y={y} width={w} height={barH} rx="3"
                  fill={up ? "var(--red)" : "var(--teal)"} />
            <text x={up ? mid + w + 8 : mid - w - 8} y={y + barH / 2 + 4}
                  className="ax-value" textAnchor={up ? "start" : "end"}>
              {c > 0 ? "+" : ""}{c.toFixed(4)}
            </text>
            <text x={690} y={y + barH / 2 + 4} className="ax-tick" textAnchor="end">
              {typeof r.value === "number"
                ? Math.abs(r.value) >= 1000
                  ? r.value.toExponential(2)
                  : r.value.toFixed(3)
                : String(r.value ?? "")}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* ----------------------------------------------------------- delta arrows */
export function DeltaBar({ before, after, label, format = (v) => pct(v, 1) }) {
  const b = Number(before) || 0;
  const a = Number(after) || 0;
  const hi = Math.max(b, a, 1e-9);
  const W = 700;
  const bw = (v) => Math.max(2, (v / hi) * (W - 250));
  return (
    <svg className="chart" viewBox={`0 0 ${W} 96`} preserveAspectRatio="xMinYMin meet">
      <text x={0} y={16} className="ax-axis">{label}</text>
      <text x={92} y={44} className="ax-label" textAnchor="end">Before</text>
      <rect x={100} y={30} width={bw(b)} height={20} rx="3" fill="var(--muted-bar)" />
      <text x={100 + bw(b) + 8} y={45} className="ax-value">{format(b)}</text>
      <text x={92} y={80} className="ax-label" textAnchor="end">After</text>
      <rect x={100} y={66} width={bw(a)} height={20} rx="3" fill="var(--teal)" />
      <text x={100 + bw(a) + 8} y={81} className="ax-value">{format(a)}</text>
    </svg>
  );
}

/* --------------------------------------------------------- stage pipeline */
export function StagePipeline({ stages }) {
  const rows = safe(stages);
  if (!rows.length) return null;
  return (
    <div className="pipeline">
      {rows.map((s, i) => (
        <span key={i} className="pipeline-step">
          <span className="pipeline-idx">{i + 1}</span>
          {String(s).replace(/_/g, " ").toLowerCase()}
          {i < rows.length - 1 && <span className="pipeline-arrow">→</span>}
        </span>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------- mini bars */
export function EntropyBar({ value, label }) {
  const v = Math.max(0, Math.min(Number(value) || 0, 1));
  return (
    <div className="entropy">
      <div className="entropy-head">
        <span>{label}</span>
        <b>{v.toFixed(3)}</b>
      </div>
      <div className="entropy-track">
        <div className="entropy-fill" style={{ width: `${v * 100}%` }} />
      </div>
    </div>
  );
}
