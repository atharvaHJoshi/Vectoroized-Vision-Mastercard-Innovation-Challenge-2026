# SovereignGuard — UI Complete Reference

> Every visual element, every data binding, every state transition, every CSS class — explained theoretically.

---

## Table of Contents

1. [System Architecture & Request Lifecycle](#1-system-architecture--request-lifecycle)
2. [Shell Layout — Sidebar, Top Bar, Main](#2-shell-layout)
3. [Design System — CSS Classes, Colours, Typography](#3-design-system)
4. [Component Catalog — Every Reusable Piece](#4-component-catalog)
5. [Page 1: Overview (Situation Room)](#5-page-1-overview)
6. [Page 2: Intelligence (Attack Taxonomy)](#6-page-2-intelligence)
7. [Page 3: Red Team (Attack Simulator)](#7-page-3-red-team)
8. [Page 4: Blue Team (Detection)](#8-page-4-blue-team)
9. [Page 5: Explain (TreeSHAP)](#9-page-5-explain)
10. [Page 6: Gap Analysis](#10-page-6-gap-analysis)
11. [Page 7: Adaptive Loop (Hero)](#11-page-7-adaptive-loop)
12. [Chart Components — SVG Rendering Theory](#12-chart-components)
13. [State Management — Lifecycle & Caching](#13-state-management)
14. [Async Job Polling System](#14-async-job-polling)
15. [Error, Loading, Empty States](#15-states)
16. [Responsive Breakpoints](#16-responsive)
17. [Proxy Configuration](#17-proxy)

---

## 1. System Architecture & Request Lifecycle

### How a User Action Reaches the Backend

```
User clicks button in browser
        │
        ▼
React event handler fires (e.g. onClick={() => simulate()})
        │
        ▼
Handler calls API helper from lib/api.js (e.g. runJob("/api/simulate", payload, onProgress))
        │
        ▼
api.js calls fetch("/api/simulate", {method: "POST", body: ...})
        │
        ▼
Browser sends HTTP request to localhost:3000/api/simulate
        │
        ▼
Next.js dev server intercepts /api/* via next.config.js rewrite rule
        │
        ▼
next.config.js proxies to http://localhost:8000/api/simulate (the Python backend)
        │
        ▼
Python server.py receives request, processes it, returns JSON
        │
        ▼
Response travels back through the proxy to the browser
        │
        ▼
api.js parses JSON, returns to React handler
        │
        ▼
Handler calls setState (e.g. setRun(result))
        │
        ▼
React re-renders affected components with new data
```

### The Proxy (next.config.js)

```javascript
// frontend/next.config.js
module.exports = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ];
  },
};
```

This means:
- Frontend code calls `fetch("/api/health")` — no hostname needed
- Next.js dev server forwards it to `http://localhost:8000/api/health`
- The browser never talks to port 8000 directly
- CORS is not needed because the browser sees everything as same-origin (port 3000)

### Why Two Servers?

| Server | Port | Purpose | Technology |
|---|---|---|---|
| Frontend | 3000 | Serves HTML/JS/CSS, proxies API calls | Next.js (Node.js) |
| Backend | 8000 | REST API, ML computation, SQLite | Python http.server |

The separation keeps the Python ML core independent of the frontend build system.

---

## 2. Shell Layout

### Visual Structure

The entire dashboard is wrapped in a flexbox layout with three zones:

```
┌──────────────────────────────────────────────────────────────┐
│ .shell (display: flex; min-height: 100vh)                    │
│                                                              │
│ ┌──────────────┐ ┌──────────────────────────────────────────┐│
│ │ .sidebar     │ │ .main                                    ││
│ │ (260px wide) │ │ (flex: 1; max-width: 1520px)            ││
│ │              │ │                                          ││
│ │ position:    │ │ ┌──────────────────────────────────────┐ ││
│ │ sticky       │ │ │ .topbar                              │ ││
│ │ top: 0       │ │ │ (RunBanner + ScalePicker)            │ ││
│ │ height:      │ │ └──────────────────────────────────────┘ ││
│ │ 100vh        │ │                                          ││
│ │ overflow-y:  │ │ ┌──────────────────────────────────────┐ ││
│ │ auto         │ │ │ <Body />                             │ ││
│ │              │ │ │ (Current page component)              │ ││
│ │              │ │ │                                      │ ││
│ │              │ │ │ .stack (display: flex; flex-direction: │ ││
│ │              │ │ │   column; gap: 16px)                  │ ││
│ │              │ │ └──────────────────────────────────────┘ ││
│ └──────────────┘ └──────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

### The Sidebar

**Structure:**

```
.sidebar
├── .brand
│   ├── .brand-mark ("SG" — gradient background)
│   └── .brand-name + .brand-tag
│
├── nav
│   └── .nav-group × 3 (Situation, Red Team, Blue Team, Adaptive)
│       └── .nav-item × 7
│           ├── .nav-dot (6px circle)
│           ├── label text
│           └── .nav-hero-tag (only on "Loop" item)
│
└── .sidebar-foot
    ├── .loop-legend (pipeline text)
    └── .health
        ├── .dot (status indicator)
        ├── status text
        └── .health-sub (ML backend info)
```

**How navigation works:**

1. Each `.nav-item` is a `<button>` with an `onClick` handler
2. The handler calls `setPage(n.id)` — updates the `page` state in the App component
3. The App component uses a lookup table to find the matching page component:
   ```javascript
   const Body = {
     overview: Overview,
     intel: Intelligence,
     redteam: RedTeam,
     blueteam: BlueTeam,
     explain: Explain,
     gap: GapAnalysis,
     loop: AdaptiveLoop,
   }[page];
   ```
4. React re-renders, replacing the `<Body>` component in the main area

**Active state styling:**

```
.nav-item.is-active
  → background: var(--surface-3)    (slightly lighter than sidebar)
  → color: var(--text)              (full brightness)
  → font-weight: 600                (bold)

.nav-item.is-active .nav-dot
  → background: var(--accent)       (blue glow for default)
  → box-shadow: 0 0 6px rgba(59, 130, 246, 0.4)

For tone-red.is-active:
  → .nav-dot background: var(--red)  (red glow)

For tone-blue.is-active:
  → .nav-dot background: var(--accent)  (blue glow)

For tone-amber.is-active:
  → .nav-dot background: var(--amber)  (amber glow)
```

**Health indicator logic:**

```javascript
// useHealth() hook in components/UI.jsx
// On mount, calls GET /api/health
// Three possible states:
health !== null && !error  → green dot, "backend online", show ml_backend
health === null && error   → red dot, "backend offline", show "run: python sg.py serve"
health === null && !error  → no dot, "connecting…"
```

### The Top Bar

```
.topbar (display: flex; gap: 12px; margin-bottom: 22px)
├── RunBanner (flex: 1)
│   ├── If run exists:
│   │   └── .runbar
│   │       ├── .runbar-k "Active run" + <code>run_id</code>
│   │       ├── .runbar-stats (3 spans: transactions, fraud %, scenarios)
│   │       └── button.btn.btn-ghost "New simulation"
│   │
│   └── If no run:
│       └── .runbar.runbar-empty
│           ├── strong "No simulation loaded."
│           └── button.btn.btn-primary "Run simulation"
│
└── .scale-pick
    ├── label text "scale"
    └── <select> with 3 options: tiny, demo, large
```

**Scale picker behavior:**

- When user changes the dropdown, `setScale(e.target.value)` is called
- The scale value is stored in App state
- It's passed to `simulate()` when the user clicks "Run simulation"
- The scale is NOT sent to the backend immediately — it's sent when simulation starts

---

## 3. Design System

### Colour Palette

| Variable | Value | Usage |
|---|---|---|
| `--bg` | `#080b12` | Page background |
| `--bg-subtle` | `#0c1019` | Slightly lighter background |
| `--surface-1` | `#0f1420` | Card backgrounds |
| `--surface-2` | `#141a28` | Input backgrounds, hover states |
| `--surface-3` | `#1a2235` | Active nav, chip backgrounds |
| `--surface-4` | `#212b42` | Button hover states |
| `--border` | `#1e2940` | Default borders |
| `--border-focus` | `#2a3a5c` | Hover/focus borders |
| `--text` | `#e8edf6` | Primary text |
| `--text-secondary` | `#8b96b0` | Descriptions, subtitles |
| `--text-muted` | `#5a6580` | Labels, captions |
| `--text-faint` | `#3d4760` | Very dim text |
| `--accent` | `#3b82f6` | Primary actions, Blue Team tone |
| `--red` | `#ef4444` | Errors, fraud, Red Team tone |
| `--green` | `#10b981` | Success, good metrics |
| `--amber` | `#f59e0b` | Warnings, Adaptive tone |
| `--violet` | `#8b5cf6` | Secondary accent |

### Tone System

Each page/card has a "tone" that controls its accent colour:

```
tone="red"   → card-red   → border-left: 3px solid var(--red)
tone="blue"  → card-blue  → border-left: 3px solid var(--accent)
tone="amber" → card-amber → border-left: 3px solid var(--amber)
(default)    → no left border
```

Tones are also used for:
- KPI cards: `.kpi-good` (green value), `.kpi-bad` (red value), `.kpi-warn` (amber value), `.kpi-info` (blue value)
- Badges: `.sev-critical` (red bg), `.sev-high` (orange bg), `.sev-medium` (amber bg), `.sev-low` (green bg)
- Risk bands: `.band-low` (green), `.band-medium` (amber), `.band-high` (orange), `.band-critical` (red)

### Typography

```
Font stacks:
  --mono: "SF Mono", "Cascadia Code", "Fira Code", "JetBrains Mono", ui-monospace, Menlo, Consolas, monospace
  --sans: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, "Helvetica Neue", Arial, sans-serif

Base: 13.5px, line-height 1.6, font-family var(--sans)

Numeric values: font-variant-numeric: tabular-nums
  → All KPI values, table cells, chart ticks, gauge values use monospace-aligned numbers

Headings:
  h1: 20px, font-weight 700, letter-spacing -0.02em
  h2: 14px, font-weight 600
  h3: 12.5px, font-weight 600
```

### Spacing & Borders

```
Border radius:
  --radius-sm: 6px   (buttons, chips, badges)
  --radius: 8px      (cards, inputs)
  --radius-lg: 12px  (hero sections, intel cards)

Gap:
  .grid: 14px between grid items
  .stack: 16px between stacked sections
  .card-body: 16px 20px 20px padding

Shadows:
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.3)  (buttons)
  --shadow: 0 2px 8px rgba(0,0,0,0.25)    (cards on hover)
  --shadow-lg: 0 4px 16px rgba(0,0,0,0.35) (hero buttons)

Transitions:
  --transition: 0.15s ease  (all hover/focus states)
```

---

## 4. Component Catalog

### 4.1 KPI Card

**Source:** `components/UI.jsx` → `Kpi({label, value, sub, tone, big})`

**Renders:**
```html
<div class="kpi kpi-{tone} {kpi-big if big}">
  <div class="kpi-label">{label}</div>
  <div class="kpi-value">{value}</div>
  <div class="kpi-sub">{sub}</div>     <!-- only if sub provided -->
</div>
```

**CSS class → visual mapping:**
```
.kpi                → background: var(--surface-1), border: 1px solid var(--border), padding: 14px 16px
.kpi:hover          → border-color: var(--border-focus)
.kpi-label          → 10.5px, uppercase, letter-spacing 0.08em, var(--text-muted)
.kpi-value          → 24px, font-weight 700, letter-spacing -0.025em
.kpi-big .kpi-value → 38px
.kpi-sub            → 11.5px, var(--text-muted), margin-top 3px
.kpi-good .kpi-value → color: var(--green)
.kpi-bad .kpi-value  → color: var(--red)
.kpi-warn .kpi-value → color: var(--amber)
.kpi-info .kpi-value → color: var(--accent)
```

**Data flow:**
```
Parent passes: <Kpi label="Recall" value={pct(m.recall, 1)} tone={m.recall >= 0.8 ? "good" : "warn"} />
                    │                      │                        │
                    │                      │                        └─ tone determines colour
                    │                      └─ pct() formats 0.603 → "60.3%"
                    └─ static label text
```

### 4.2 Card

**Source:** `components/UI.jsx` → `Card({title, subtitle, children, actions, tone})`

**Renders:**
```html
<section class="card card-{tone}">
  <header class="card-head">
    <div>
      <h2>{title}</h2>
      <p class="card-sub">{subtitle}</p>
    </div>
    <div class="card-actions">{actions}</div>
  </header>
  <div class="card-body">{children}</div>
</section>
```

**CSS class → visual mapping:**
```
.card           → background: var(--surface-1), border: 1px solid var(--border), border-radius: 12px
.card:hover     → border-color: var(--border-focus)
.card-red       → border-left: 3px solid var(--red)
.card-blue      → border-left: 3px solid var(--accent)
.card-amber     → border-left: 3px solid var(--amber)
.card-head      → display: flex, justify-content: space-between, padding: 16px 20px 0
.card-sub       → 12px, var(--text-muted), max-width: 80ch
.card-body      → padding: 16px 20px 20px
```

**Note:** If neither `title` nor `actions` is provided, the `<header>` is not rendered at all.

### 4.3 Table

**Source:** `components/UI.jsx` → `Table({columns, rows, empty, rowKey})`

**Column definition:**
```javascript
{
  key: "recall",           // field name in row object
  header: "Recall",        // column header text
  align: "right",          // text-align (default: "left")
  width: "22%",            // optional CSS width
  render: (r) => pct(r.recall, 1),  // optional custom renderer
  cellStyle: (r) => ({background: recallColour(r.recall)}),  // optional inline styles
}
```

**Renders:**
```html
<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th style="text-align: {align}">{header}</th>  × number of columns
      </tr>
    </thead>
    <tbody>
      <tr style={row.__rowStyle}>                       × number of rows
        <td style="text-align: {align}; {cellStyle}">   × number of columns
          {render ? render(row) : String(row[key])}
        </td>
      </tr>
    </tbody>
  </table>
</div>
```

**If rows is empty:** renders `<div class="chart-empty">{empty}</div>` instead of the table.

**CSS class → visual mapping:**
```
table                → width: 100%, border-collapse: collapse, font-size: 12.5px
thead th             → 10.5px, uppercase, letter-spacing 0.08em, var(--text-muted), border-bottom: 1px solid var(--border)
tbody td             → padding: 9px 12px, border-bottom: 1px solid var(--bg-subtle)
tbody tr:hover       → background: var(--surface-2)
```

### 4.4 Badge

**Source:** `components/UI.jsx` → `Badge({children, className})`

**Renders:** `<span class="badge {className}">{children}</span>`

**CSS class → visual mapping:**
```
.badge          → 10px, uppercase, letter-spacing 0.06em, padding: 2px 8px, border-radius: 4px
                 background: var(--surface-3), color: var(--text-secondary)

.sev-critical   → background: var(--red-dim), color: var(--red)
.sev-high       → background: rgba(251,146,60,0.12), color: #fb923c
.sev-medium     → background: var(--amber-dim), color: var(--amber)
.sev-low        → background: var(--green-dim), color: var(--green)

.band-low       → background: var(--green-dim), color: var(--green)
.band-medium    → background: var(--amber-dim), color: var(--amber)
.band-high      → background: rgba(251,146,60,0.12), color: #fb923c
.band-critical  → background: var(--red-dim), color: var(--red)
```

**Usage:** `<Badge className={bandClass(d.risk_band)}>{d.risk_band}</Badge>`

### 4.5 Button

**CSS class → visual mapping:**
```
.btn                → background: var(--surface-3), border: 1px solid var(--border), border-radius: 6px
                      padding: 8px 16px, font-weight: 600, cursor: pointer
.btn:hover          → background: var(--surface-4), border-color: var(--border-focus), box-shadow: var(--shadow-sm)
.btn:active         → transform: translateY(1px)  (pressed effect)
.btn:disabled       → opacity: 0.4, cursor: not-allowed

.btn-primary        → background: var(--accent), border-color: var(--accent), color: #fff
.btn-primary:hover  → background: var(--accent-hover), box-shadow: 0 2px 8px rgba(59,130,246,0.3)

.btn-red            → background: var(--red), border-color: var(--red), color: #fff
.btn-red:hover      → background: #f87171, box-shadow: 0 2px 8px rgba(239,68,68,0.3)

.btn-ghost          → background: transparent
.btn-ghost:hover    → background: var(--surface-2)

.btn-hero           → background: linear-gradient(135deg, var(--accent), var(--violet))
                      border: 0, color: #fff, font-size: 14px, font-weight: 700, padding: 14px 32px
```

### 4.6 Chip (Toggle Button)

**CSS class → visual mapping:**
```
.chip           → border-radius: 999px (pill shape), border: 1px solid var(--border)
                  background: var(--surface-2), color: var(--text-secondary)
.chip:hover     → border-color: var(--border-focus), color: var(--text)
.chip.on        → background: var(--red-dim), border-color: var(--red), color: var(--red)
.chip-blue.on   → background: var(--accent-dim), border-color: var(--accent), color: var(--accent)
```

**Used in:** Red Team page (attack family selection), Adaptive Loop (mode selection)

### 4.7 Skeleton (Loading Placeholder)

**Source:** `components/UI.jsx` → `Skeleton({lines, height})`

**Renders:**
```html
<div class="skeleton-group">
  <div class="skeleton" style="height: 18px; width: 100%"></div>
  <div class="skeleton" style="height: 18px; width: 93%"></div>
  <div class="skeleton" style="height: 18px; width: 86%"></div>
  ...
</div>
```

**CSS animation:**
```css
.skeleton {
  background: linear-gradient(90deg, var(--surface-2) 25%, var(--surface-3) 50%, var(--surface-2) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

Each bar gets progressively narrower (`width: 100%`, `93%`, `86%`, etc.) to look like text lines.

### 4.8 Progress Log

**Source:** `components/UI.jsx` → `ProgressLog({lines, running, title})`

**Renders:**
```html
<div class="log">
  <div class="log-head">
    {running && <span class="spinner"></span>}
    {title}
  </div>
  <ol>
    {lines.map((l, i) => <li key={i}>{l}</li>)}
  </ol>
</div>
```

**CSS:**
```
.log          → background: var(--bg), border: 1px solid var(--border), border-radius: 8px
                padding: 12px 16px, max-height: 280px, overflow-y: auto
.log li       → font-family: var(--mono), font-size: 11.5px, color: var(--text-secondary)
.spinner      → 12px circle, border: 2px solid var(--border), border-top-color: var(--accent)
                animation: spin 0.7s linear infinite
```

**How it updates:** The parent passes a growing `lines` array. Each time a new progress message arrives from the backend, `setProgress((p) => [...p, message])` is called, which triggers a re-render, and the new `<li>` appears at the bottom.

### 4.9 ErrorNote

**Source:** `components/UI.jsx` → `ErrorNote({error, onRetry})`

**Renders:**
```html
<div class="note note-error">
  <strong>Something went wrong</strong>
  <p>{error.message}</p>
  {onRetry && <button class="btn btn-ghost" onClick={onRetry}>Try again</button>}
</div>
```

**CSS:** `note-error → background: var(--red-dim), border: 1px solid var(--red-soft)`

### 4.10 EmptyState

**Source:** `components/UI.jsx` → `EmptyState({title, body, action})`

**Renders:**
```html
<div class="note note-empty">
  <strong>{title}</strong>
  {body && <p>{body}</p>}
  {action}
</div>
```

**CSS:** `note-empty → background: var(--surface-1), border: 1px dashed var(--border), border-radius: 12px`

### 4.11 EntropyBar

**Source:** `components/Charts.jsx` → `EntropyBar({value, label})`

**Renders:**
```html
<div class="entropy">
  <div class="entropy-head">
    <span>{label}</span>
    <b>{value.toFixed(3)}</b>
  </div>
  <div class="entropy-track">
    <div class="entropy-fill" style="width: {value * 100}%"></div>
  </div>
</div>
```

**CSS:**
```
.entropy-track  → height: 5px, background: var(--surface-3), border-radius: 3px
.entropy-fill   → height: 100%, background: var(--accent), border-radius: 3px
                  width is set dynamically to value × 100%
```

**Theory:** Entropy measures diversity. 1.0 = perfectly even coverage across all values (maximum diversity). 0 = everything collapsed to one value (no diversity). The bar visually shows how close the attack generation is to full coverage.

### 4.12 StagePipeline

**Source:** `components/Charts.jsx` → `StagePipeline({stages})`

**Renders:**
```html
<div class="pipeline">
  <span class="pipeline-step">
    <span class="pipeline-idx">1</span>
    recon login
    <span class="pipeline-arrow">→</span>
  </span>
  <span class="pipeline-step">
    <span class="pipeline-idx">2</span>
    credential change
    <span class="pipeline-arrow">→</span>
  </span>
  ...
</div>
```

**CSS:**
```
.pipeline-step  → display: inline-flex, font-size: 11.5px, background: var(--surface-2)
                  border: 1px solid var(--border), border-radius: 6px, padding: 4px 10px
                  text-transform: capitalize
.pipeline-idx   → font-size: 9px, font-weight: 600, color: var(--text-muted), font-family: var(--mono)
.pipeline-arrow → color: var(--text-muted), margin-left: 2px
```

---

## 5. Page 1: Overview

### Purpose
The situation room. Shows the most important metrics at a glance after building a simulation. Designed to answer: "Is our defence working?"

### Layout

```
.page-head (h1 "Situation Overview" + description paragraph)

[ErrorNote if simError]  [ProgressLog if busy]

If no run:
  EmptyState "No simulation loaded" + "Run simulation" button

If run exists:
  ┌─────────────────────────────────────────────────────┐
  │ .grid.grid-4 (4 KPI cards in a row)                 │
  │ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐       │
  │ │ Recall │ │Precis. │ │   F1   │ │  FPR   │       │
  │ │60.3%   │ │45.2%   │ │0.517   │ │0.93%   │       │
  │ │good    │ │info    │ │        │ │good    │       │
  │ └────────┘ └────────┘ └────────┘ └────────┘       │
  ├─────────────────────────────────────────────────────┤
  │ .grid.grid-4 (4 more KPI cards)                     │
  │ ┌──────────┐ ┌────────┐ ┌──────────┐ ┌─────────┐  │
  │ │Txns      │ │Preval. │ │Attacks   │ │Missed   │  │
  │ │31,000    │ │1.19%   │ │120       │ │31       │  │
  │ │30 day    │ │310     │ │7 families│ │bad      │  │
  │ └──────────┘ └────────┘ └──────────┘ └─────────┘  │
  ├─────────────────────────────────────────────────────┤
  │ .grid.grid-2 (2 cards side by side)                 │
  │ ┌──────────────────────┐ ┌──────────────────────┐  │
  │ │ Risk-band            │ │ Operating curve      │  │
  │ │ distribution         │ │                      │  │
  │ │ [StackedBar]         │ │ [LineChart]          │  │
  │ │ [Table: band/action/ │ │ recall + precision   │  │
  │ │  fraud/legit/%]      │ │ vs FPR budget        │  │
  │ └──────────────────────┘ └──────────────────────┘  │
  ├─────────────────────────────────────────────────────┤
  │ Card "Where to go next"                             │
  │ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
  │ │Red Team →│ │Gap →     │ │Loop →    │            │
  │ └──────────┘ └──────────┘ └──────────┘            │
  └─────────────────────────────────────────────────────┘
```

### Data Flow

```
1. Page mounts
2. useEffect checks: if run exists but detect is null → call load()
3. load() calls POST /api/detect {run_id}
4. Backend returns detection results
5. setDetect(result) stores in shared state
6. Page re-renders with all data

Simultaneously:
- simError shows if simulation failed
- ProgressLog shows if simulation is running
- EmptyState shows if no simulation exists
```

### KPI Tone Logic

```javascript
// Recall KPI
tone={m.recall >= 0.8 ? "good" : m.recall >= 0.6 ? "warn" : "bad"}
// ≥80% = green, 60-80% = amber, <60% = red

// FPR KPI
tone={m.fpr <= 0.012 ? "good" : "warn"}
// ≤1.2% = green, >1.2% = amber

// Missed attacks KPI
tone="bad"  // always red — misses are always concerning
```

### Risk-Band Distribution

The stacked bar shows how traffic is routed across the 4 risk bands:

```
|← LOW (green) →|← MEDIUM (amber) →|← HIGH (orange) →|← CRITICAL (red) →|
         ALLOW           MONITOR        STEP_UP_AUTH       HOLD_REVIEW
```

The table below shows the exact counts:
| Band | Action | Total Count | Fraud Count | Legit Count | % of All Fraud |
|---|---|---|---|---|---|
| LOW | ALLOW | 6,025 | 26 | 5,999 | 33.3% |
| MEDIUM | MONITOR | 79 | 5 | 74 | 6.4% |
| HIGH | STEP_UP_AUTH | 72 | 16 | 56 | 20.5% |
| CRITICAL | HOLD_REVIEW | 32 | 31 | 1 | 39.7% |

**Theory:** CRITICAL band catches only 1 legit transaction but captures 31 of 78 fraud events (39.7%). This is the "high-friction, high-capture" zone.

### Operating Curve

The line chart shows two curves:
- **Recall (solid, green):** As FPR budget increases, recall improves
- **Precision (dashed, blue):** As FPR budget increases, precision degrades

Each dot is a deployable operating point. The business chooses where on this curve to operate.

---

## 6. Page 2: Intelligence

### Purpose
Read-only reference for the attack taxonomy. Provides context for what the Red Team generates and what the Blue Team defends against.

### Layout

```
.page-head (h1 "Attack Intelligence" + description)

Card "Why generative AI changes the problem" (amber tone)
  └── taxonomy.genai_amplification_note

.intel (stack of 7 attack cards)
  └── .intel-card × 7
      ├── .intel-top
      │   ├── .intel-name ("Account Takeover")
      │   ├── .intel-family ("identity_theft · 6 stages · prior 0.08")
      │   ├── .intel-target ("Target: ...")
      │   ├── .surfaces (badges: CARD, UPI, WALLET)
      │   └── [severity badge] [Detail/Less button]
      ├── StagePipeline (stages: RECON_LOGIN → CREDENTIAL_CHANGE → ...)
      ├── .intel-grid (2 columns)
      │   ├── "Role of generative AI" (paragraph)
      │   └── "Signals a defender can use" (sig badges)
      └── (if expanded)
          ├── .intel-grid
          │   ├── "Behavioural changes" (bulleted list)
          │   └── "Mitigations" (bulleted list)
          └── .hard-note ("What the hard variant looks like: ...")

Card "Difficulty levels" (2-column grid)
  └── 4 difficulty badges + descriptions

Card "Cross-cutting patterns"
  └── Pattern items (name, description, implication)
```

### Data Flow

```
1. Page mounts
2. useEffect calls GET /api/taxonomy
3. Backend loads data/attack_taxonomy.json
4. setTax(taxonomy) stores locally
5. Page renders taxonomy data

No shared state used — this page is self-contained.
```

### Expand/Collapse

```javascript
// Local state: open = {ACCOUNT_TAKEOVER: true, TRANSACTION_MANIPULATION: false, ...}
const [open, setOpen] = useState({});

// Toggle handler:
onClick={() => setOpen((o) => ({ ...o, [a.attack_type]: !isOpen }))}

// Conditional rendering:
{isOpen && (
  <>
    {/* Behavioural changes + mitigations lists */}
    {/* Hard variant note */}
  </>
)}
```

---

## 7. Page 3: Red Team

### Purpose
Configure and generate attack campaigns. The user controls which families, how stealthy, and how many.

### Layout

```
.page-head (h1 "Red Team Simulator" + description)

If no run:
  EmptyState + "Run simulation" button

If run exists:
  Card "Configure attack campaign" (red tone)
  ├── Attack family chips (7 chips, all on by default)
  ├── .controls
  │   ├── Difficulty selector (dropdown: EASY/MEDIUM/HARD/ADVERSARIAL)
  │   ├── Scenario count input (number, 1–20000, default 300)
  │   └── "Generate attacks" button (red)
  └── Difficulty description (small text below controls)

  [ErrorNote if error]

  If result exists:
    ┌──────────────────────────────────────────────────┐
    │ .grid.grid-4 (4 KPI cards)                       │
    │ ┌──────────┐ ┌────────┐ ┌──────────┐ ┌────────┐│
    │ │Scenarios │ │Events  │ │Victims   │ │Amount  ││
    │ │300       │ │2,947   │ │180       │ │span    ││
    │ │bad       │ │        │ │7 personas│ │10^3.7  ││
    │ └──────────┘ └────────┘ └──────────┘ └────────┘│
    ├──────────────────────────────────────────────────┤
    │ .grid.grid-2                                     │
    │ ┌──────────────────┐ ┌──────────────────┐       │
    │ │ Measured         │ │ Composition      │       │
    │ │ diversity        │ │                  │       │
    │ │ [EntropyBar ×5]  │ │ [BarChart: type] │       │
    │ │ devices/cities/  │ │ [BarChart: diff] │       │
    │ │ merchants/stages │ │                  │       │
    │ └──────────────────┘ └──────────────────┘       │
    ├──────────────────────────────────────────────────┤
    │ Card "Sample scenarios"                          │
    │ [Table: ID, Family, Skill, Persona, Events,     │
    │  Total value, Span]                              │
    ├──────────────────────────────────────────────────┤
    │ Card "Sample events"                             │
    │ [Table: Txn, Stage, Amount, Method, Type, City, │
    │  Skill]                                          │
    └──────────────────────────────────────────────────┘
```

### Data Flow

```
1. Page mounts
2. useEffect calls GET /api/config → populates attack_types list and difficulty descriptions
3. User clicks chips to toggle families on/off (local state: types)
4. User selects difficulty (local state: difficulty)
5. User sets scenario count (local state: n)
6. User clicks "Generate attacks"
7. setRunning(true) → button shows "Generating…"
8. POST /api/redteam/generate {run_id, n_scenarios, attack_types, difficulty} → returns 202 + job_id
9. Client polls GET /api/jobs/{job_id}; progress lines stream into a ProgressLog
10. setResult(result) → page renders results
11. setRunning(false) → button returns to normal
```

### Chip Toggle Logic

```javascript
const toggle = (t) =>
  setTypes((cur) =>
    cur.includes(t)
      ? cur.filter((x) => x !== t)    // remove if present
      : [...cur, t]                     // add if absent
  );
```

When all chips are deselected, the backend generates from all families (null = all).

### Entropy Bars

The diversity section shows 5 entropy bars, one for each dimension:

| Dimension | What 1.0 means | What 0 means |
|---|---|---|
| Attack family | All 7 families equally represented | Only 1 family used |
| Evasion skill | All 4 difficulty levels equally used | Only 1 difficulty used |
| Victim persona | All 7 personas equally targeted | Only 1 persona targeted |
| Geography | All 20 cities equally used | Only 1 city used |
| Attack stage | All stages equally represented | Only 1 stage used |

---

## 8. Page 4: Blue Team

### Purpose
Comprehensive detection results. The most data-dense page — 12 KPIs, 4 charts, and a friction breakdown.

### Layout

```
.page-head (h1 "Blue Team Detection" + description)

If no run: EmptyState

If run exists:
  Card "Detector performance on the held-out test window" (blue tone)
  ├── Header subtitle: "Operating threshold {value}, chosen on validation at {fpr} FPR budget"
  ├── "Re-run detection" button (ghost)
  │
  ├── Row 1: .grid.grid-4
  │   ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
  │   │Recall  │ │Precis. │ │   F1   │ │  FPR   │
  │   │60.3%   │ │45.2%   │ │0.517   │ │0.93%   │
  │   └────────┘ └────────┘ └────────┘ └────────┘
  │
  ├── Row 2: .grid.grid-4 (margin-top: 14px)
  │   ┌──────────┐ ┌──────┐ ┌──────────┐ ┌──────────┐
  │   │ROC-AUC   │ │PR-AUC│ │Value     │ │Latency   │
  │   │0.9530    │ │0.6089│ │caught    │ │9.6 µs    │
  │   └──────────┘ └──────┘ │60.3%     │ │per txn   │
  │                         └──────────┘ └──────────┘
  │
  └── Row 3: .grid.grid-4 (margin-top: 14px)
      ┌────┐ ┌────┐ ┌────┐ ┌──────────────┐
      │ TP │ │ FN │ │ FP │ │Alerts/1k     │
      │ 47 │ │ 31 │ │ 57 │ │9.30          │
      └────┘ └────┘ └────┘ └──────────────┘

  ┌──────────────────────────────────────────────────┐
  │ .grid.grid-2                                     │
  │ ┌──────────────────┐ ┌──────────────────┐       │
  │ │Recall by         │ │Recall by         │       │
  │ │evasion skill     │ │attack family     │       │
  │ │[BarChart]        │ │[BarChart]        │       │
  │ │EASY=100%         │ │MERCHANT_F=100%   │       │
  │ │MEDIUM=52%        │ │MULTI_STAGE=52%   │       │
  │ │HARD=17%          │ │ACCOUNT_T=29%     │       │
  │ └──────────────────┘ └──────────────────┘       │
  ├──────────────────────────────────────────────────┤
  │ .grid.grid-2                                     │
  │ ┌──────────────────┐ ┌──────────────────┐       │
  │ │Operating curve   │ │Feature importance │       │
  │ │[LineChart]       │ │[BarChart]        │       │
  │ │+ [Table]         │ │top 14 features   │       │
  │ └──────────────────┘ └──────────────────┘       │
  ├──────────────────────────────────────────────────┤
  │ Card "Customer friction"                         │
  │ .grid.grid-4                                     │
  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐│
  │ │Legit     │ │Fraud     │ │Fraud     │ │Legit ││
  │ │challenged│ │stopped   │ │allowed   │ │allow ││
  │ │0.93%     │ │60.3%     │ │39.7%     │ │99.1% ││
  │ └──────────┘ └──────────┘ └──────────┘ └──────┘│
  └──────────────────────────────────────────────────┘
```

### Bar Chart Colour Logic

```javascript
// Recall by difficulty and by family:
colour:
  r.recall >= 0.9 ? "var(--green)" :    // good — high recall
  r.recall >= 0.7 ? "var(--amber)" :    // warning — moderate recall
  "var(--red)"                           // bad — low recall

// Feature importance:
colour: "var(--accent)"  // all bars blue — just showing magnitude
```

### Customer Friction Theory

The friction card shows the business cost of detection:

| Metric | What it means | Ideal value |
|---|---|---|
| Legit challenged | Honest customers who faced step-up auth or hold | < 2% |
| Fraud stopped | Fraud that was caught (challenged or held) | High (matches recall) |
| Fraud allowed through | Fraud that slipped past all controls | Low |
| Legit allowed straight through | Honest customers who had zero friction | > 98% |

The tradeoff: higher recall means more fraud stopped, but also more legit customers challenged.

---

## 9. Page 5: Explain

### Purpose
Per-transaction TreeSHAP explainability. Shows exactly why the model made a specific decision, feature by feature.

### Layout

```
.page-head (h1 "Explainability" + description)

If no run: EmptyState

If run exists:
  Card "Pick a transaction to explain" (blue tone)
  ├── "Explain the worst miss" button (primary)
  ├── Row index input (number, default 0)
  ├── "Explain row" button
  └── Explanation text ("Worst miss" finds the most confident miss)

  [ErrorNote if error]
  [Skeleton if loading]

  If data exists:
    .grid.grid-2
    ┌──────────────────────┐ ┌──────────────────────┐
    │ Risk decision        │ │ Transaction          │
    │                      │ │                      │
    │ ┌──────┐ ┌────────┐ │ │ [Table: 11 rows]     │
    │ │Gauge │ │Details │ │ │ Txn ID, Customer,    │
    │ │SVG   │ │Action  │ │ │ Merchant, Amount,    │
    │ │0-100 │ │Prob    │ │ │ Method, Type, City,  │
    │ │      │ │Band    │ │ │ Auth, Attack family, │
    │ │      │ │Truth   │ │ │ Attack stage, Skill  │
    │ │      │ │Correct │ │ │                      │
    │ └──────┘ └────────┘ │ │                      │
    │ [Narrative note]     │ │                      │
    └──────────────────────┘ └──────────────────────┘

    Card "Why — SHAP contributions"
    ├── Subtitle: "Base value {x}. Red bars pushed up, teal bars pushed down."
    ├── [Waterfall chart — bidirectional SVG]
    └── Legend: risk-increasing (red) / protective (teal)

    .grid.grid-2
    ┌──────────────────────┐ ┌──────────────────────┐
    │ Risk drivers         │ │ Protective factors   │
    │ [Table]              │ │ [Table]              │
    │ Factor | Value | +φ  │ │ Factor | Value | -φ  │
    │ (red contribution)   │ │ (green contribution) │
    └──────────────────────┘ └──────────────────────┘
```

### Data Flow

```
User clicks "Explain the worst miss"
  │
  ├─→ setLoading(true)
  ├─→ POST /api/score {run_id, worst_missed: true}
  │     → Backend finds fraud txn with lowest model probability
  │     → Runs TreeSHAP, computes risk decision, generates narrative
  │     → Returns full result
  ├─→ setData(result)
  ├─→ setLoading(false)
  └─→ Page renders with explanation

User enters row index and clicks "Explain row"
  │
  ├─→ POST /api/score {run_id, index: 42}
  │     → Backend explains that specific row
  └─→ Same rendering flow
```

### Gauge Theory

The gauge is an SVG semi-circle showing risk score 0–100:

```
         ┌─────────────┐
        /    CRITICAL    \
       /    (80-100)      \
      │                    │
      │    ┌────────┐     │
      │    │  1.1   │     │  ← numerical value
      │    │  LOW   │     │  ← band label
      │    └────────┘     │
      │         │          │  ← needle pointing to score
       \                 /
        \   LOW (0-30)  /
         └─────────────┘

Arc colours (background):
  0-30%:   rgba(45,212,191,0.35)  (teal/green tint)
  30-60%:  rgba(250,204,21,0.35)  (amber tint)
  60-80%:  rgba(251,146,60,0.4)   (orange tint)
  80-100%: rgba(248,113,113,0.45) (red tint)

Needle: black line from center to score position
Center dot: 5px black circle
Value text: 26px monospace, centred above needle
Band text: 10px uppercase, centred below needle
```

### Waterfall Theory

The SHAP waterfall shows feature contributions bidirectionally:

```
                                    ← more protective          more risky →
                                    │                           │
Feature label          │            │              ████████████ │  +0.196
Age of device          │            │              ████████████ │  +0.158
High-risk location     │            │              ████████     │
                       │            │                           │
...                    │            │                           │
                       │            │                           │
Prior txn w/ merchant  ████████████ │            │              │  -1.444
Digital footprint      █████████    │            │              │  -0.852
A2A transfer           ██████       │            │              │  -0.673
                                    │            │              │
                                   baseline      model output
```

**Left side (green/teal bars):** Protective factors — features that pushed the score DOWN (toward legitimate).

**Right side (red bars):** Risk factors — features that pushed the score UP (toward fraud).

**Far right column:** Raw feature values (e.g., "18.968", "1.0", "12.0").

**Theory:** The sum of all contributions plus the base value equals the model's output. This is the "local accuracy" property of SHAP values.

---

## 10. Page 6: Gap Analysis

### Purpose
Explains why attacks evade detection. Identifies specific evasion traits and attributes how much of the failure each trait explains.

### Layout

```
.page-head (h1 "Gap Analysis" + description)

If no run: EmptyState

If gap exists:
  Card (amber) — headline summary
  ┌──────────────────────────────────────────────────┐
  │ .grid.grid-4                                     │
  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐│
  │ │Tested    │ │Detected  │ │Evaded    │ │Recall││
  │ │78        │ │47        │ │31        │ │60.3% ││
  │ └──────────┘ └──────────┘ └──────────┘ └──────┘│
  ├──────────────────────────────────────────────────┤
  │ Card "Attribution"                               │
  │ [BarChart: attribution values per hypothesis]    │
  │ tallest bar = most explanatory trait             │
  ├──────────────────────────────────────────────────┤
  │ Card "Evasion traits in detail"                  │
  │ [Table: Trait | %misses | %catches | Lift |     │
  │  Attribution | Remediation]                      │
  ├──────────────────────────────────────────────────┤
  │ .grid.grid-2                                     │
  │ ┌──────────────────┐ ┌──────────────────┐       │
  │ │Weakest segments  │ │By attack family  │       │
  │ │[Table: family/   │ │[BarChart]        │       │
  │ │ skill/n/missed/  │ │worst first       │       │
  │ │ recall heatmap]  │ │                  │       │
  │ └──────────────────┘ └──────────────────┘       │
  ├──────────────────────────────────────────────────┤
  │ Card "Worked examples"                           │
  │ [Table: Attack | Family | Skill | Stage |        │
  │  Amount | ×normal | Score | Traits]              │
  ├──────────────────────────────────────────────────┤
  │ Card (amber) "Next step"                         │
  │ └── button.btn.btn-hero "Run the adaptive loop →"│
  └──────────────────────────────────────────────────┘
```

### Attribution Theory

The attribution column measures how much each evasion trait explains the detection failure:

```
attribution = (share_of_missed - share_of_detected) × share_of_missed
```

- `share_of_missed`: What % of missed attacks have this trait
- `share_of_detected`: What % of caught attacks have this trait
- `lift`: share_of_missed / share_of_detected (how much more common in misses)

**Example:**
- Merchant mimicry: 87% of misses, 45% of catches → lift 1.95×, attribution 22%
- This means: merchant mimicry explains 22% of the total detection failure

**Why not just use lift?** A trait present in 100% of misses but also 100% of catches has infinite lift but zero attribution — it doesn't distinguish misses from catches.

### Weakest Segments Heatmap

The table uses `recallColour(r.recall)` to tint each cell:

```javascript
function recallColour(r) {
  if (r >= 0.95) return "rgba(16,185,129,0.28)";   // dark green
  if (r >= 0.85) return "rgba(16,185,129,0.16)";   // light green
  if (r >= 0.7)  return "rgba(245,158,11,0.18)";   // amber
  if (r >= 0.5)  return "rgba(251,146,60,0.22)";   // orange
  return "rgba(239,68,68,0.26)";                     // red
}
```

This creates a heatmap effect: green cells are segments where the defence works, red cells are where it fails.

---

## 11. Page 7: Adaptive Loop

### Purpose
The hero screen. Diagnoses weaknesses, generates targeted attacks, retrains, and measures improvement on a held-out adversarial batch.

### Layout

```
.hero (gradient background, 28px padding)
├── h1 "Adaptive Attack / Defence Loop"
├── p.hero-sub (description)
└── .controls (if run exists)
    ├── Adversarial scenarios input (number, default 200)
    ├── Search rounds input (number, default 2)
    ├── Mode chips (score-guided search / interpretable only)
    └── button.btn.btn-hero "Run adaptive loop"

If no run: EmptyState
[ErrorNote if error]
[ProgressLog if running or progress]

If loop result exists:
  Card "Result on the held-out adversarial batch" (amber tone)
  ├── .ba (before/after comparison)
  │   ├── .ba-side
  │   │   ├── .ba-tag "Before — baseline defence"
  │   │   ├── .ba-metric "23.4%" (recall)
  │   │   └── .ba-rows (Precision, F1, PR-AUC, Attacks missed, FPR)
  │   │
  │   ├── .ba-arrow
  │   │   ├── → (arrow)
  │   │   ├── .ba-delta "-0.035" (recall change)
  │   │   └── "RECALL" label
  │   │
  │   └── .ba-side.after
  │       ├── .ba-tag "After — hardened defence"
  │       ├── .ba-metric "19.9%" (recall, green)
  │       └── .ba-rows (same metrics)
  │
  └── .matched-note ("FPR held at {fpr} on both sides")

  .grid.grid-4 (4 KPI cards)
  ┌──────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐
  │Recall    │ │F1      │ │PR-AUC    │ │Attacks   │
  │gain      │ │gain    │ │gain      │ │now caught│
  │-0.035    │ │-0.044  │ │+0.035    │ │-31       │
  │bad       │ │bad     │ │good      │ │good      │
  └──────────┘ └────────┘ └──────────┘ └──────────┘

  .grid.grid-2
  ┌──────────────────┐ ┌──────────────────┐
  │Metric movement   │ │Regression check  │
  │[DeltaBar ×3]     │ │[DeltaBar]        │
  │Recall before/    │ │Recall on         │
  │F1 before/after   │ │baseline attacks  │
  │PR-AUC before/    │ │[Table]           │
  │after             │ │                  │
  └──────────────────┘ └──────────────────┘

  Card "What the Red Team decided to do" (red tone)
  └── .move × N
      ├── .move-head
      │   ├── .move-cause ("Merchant mimicry")
      │   ├── .move-lift ("lift 1.95×")
      │   ├── Badge ("87% of misses")
      │   └── Badge ("knob: merchant_reuse")
      └── .move-body (rationale text)

  Card "Evasion search" (if search was used)
  └── [Table: Round | Intensity | Candidates | Kept | Mean score (all) | Mean score (kept)]

  Card "Run detail"
  └── [Table: Property | Value pairs]
```

### Data Flow

```
1. Page mounts
2. useEffect: if loop is null, calls GET /api/loop/latest
   → If a previous loop result exists, adopt it
3. User configures parameters (local state: nAdv, rounds, useSearch)
4. User clicks "Run adaptive loop"
5. setRunning(true)
6. POST /api/loop {run_id, n_adversarial, use_search, search_rounds}
7. Backend returns {job_id}
8. Polling begins (every 2s):
   → GET /api/jobs/{job_id}
   → Progress messages added to local state
   → ProgressLog renders them
9. Job completes → result stored in setLoop (shared state)
10. Page renders full before/after comparison
```

### Before/After Comparison Theory

The `.ba` layout uses a 3-column grid:

```
┌─────────────────┐     ┌─────────────────┐
│ BEFORE           │     │ AFTER            │
│ baseline defence │ →   │ hardened defence │
│                  │ Δ   │                  │
│ 23.4% recall     │     │ 19.9% recall     │
│ 0.781 precision  │     │ 0.765 precision  │
│ 0.360 F1         │     │ 0.315 F1         │
│ 0.555 PR-AUC     │     │ 0.591 PR-AUC     │
│ 679 missed       │     │ 710 missed       │
│ 0.98% FPR        │     │ 0.92% FPR        │
└─────────────────┘     └─────────────────┘
              ↑
         .ba-arrow
         "→" + delta value
```

**Theory:** The comparison is fair because:
1. Both sides use the same held-out adversarial batch (adv_eval)
2. Both sides have the same FPR budget (1%)
3. The threshold was calibrated separately for each model at that budget

### DeltaBar Chart Theory

Each DeltaBar shows a horizontal before/after comparison:

```
                        Before
Recall          ████████████████████  0.234
                After
                ██████████████████    0.199
```

The bar width is proportional to the value. Green bars for "after" if the metric improved.

### Adaptation Plan Moves

Each move represents an auditable knob change:

```
┌──────────────────────────────────────────────────────────┐
│ Merchant mimicry            lift 1.95×    87% of misses  │
│ knob: merchant_reuse                                         │
│                                                          │
│ Acceptance-side novelty is being caught, so cash out     │
│ through merchants the victim already transacts with.     │
└──────────────────────────────────────────────────────────┘
```

**Theory:** The Red Team doesn't just generate random harder attacks. It reads the gap analysis, identifies which specific evasion traits are most explanatory, and adjusts the corresponding Knobs parameters. Each move is justified by a measured weakness.

---

## 12. Chart Components

### 12.1 BarChart

**Source:** `components/Charts.jsx`

**Input:**
```javascript
{
  data: [
    { label: "ACCOUNT_TAKEOVER", value: 0.286, colour: "var(--red)" },
    { label: "MULTI_STAGE", value: 0.522, colour: "var(--amber)" },
    ...
  ],
  height: 230,         // SVG viewport height
  format: (v) => pct(v, 1),  // value formatter
  max: 1,              // max value for bar width calculation
  emptyLabel: "No data"
}
```

**SVG rendering:**
```
For each data point:
  1. Calculate bar width: (value / maxValue) × (700 - labelW - 78)
  2. Position vertically: i × (barH + gap) + 4
  3. Render:
     <text> label (right-aligned at x=180)
     <rect> bar (x=190, width=calculated, height=26, fill=colour)
     <text> formatted value (after bar)
```

**ViewBox:** `0 0 700 {height}` with `preserveAspectRatio="xMinYMin meet"`

### 12.2 LineChart

**Input:**
```javascript
{
  series: [
    {
      name: "recall",
      colour: "var(--green)",
      showDots: true,
      dashed: false,
      points: [[0.1, 0.3], [0.5, 0.7], [1.0, 0.9], ...]  // [x, y] pairs
    },
    {
      name: "precision",
      colour: "var(--accent)",
      dashed: true,
      showDots: true,
      points: [[0.1, 0.9], [0.5, 0.6], [1.0, 0.4], ...]
    }
  ],
  xLabel: "false-positive rate (%)",
  yLabel: "rate",
  xFormat: (v) => v.toFixed(1),
  yFormat: (v) => v.toFixed(2),
  height: 260
}
```

**SVG rendering:**
```
1. Compute data range: x0, x1, y0=0, y1=max(ys)
2. Create scale functions: sx(v), sy(v)
3. Draw grid lines (5 horizontal lines)
4. Draw x-axis ticks (5 labels)
5. Draw y-axis ticks (5 labels)
6. For each series:
   a. Draw <polyline> connecting all points
   b. If dashed: strokeDasharray="5 4"
   c. If showDots: draw <circle> at each point (r=3.5)
7. Draw axis labels
8. If multiple series: draw legend in top-right
```

### 12.3 Gauge

**Input:**
```javascript
{
  value: 1.1,          // risk score (0–100)
  max: 100,
  label: "risk score / 100",
  band: "LOW"
}
```

**SVG rendering:**
```
1. Semi-circle from π to 0 (left to right, top half)
2. 4 arc segments (coloured backgrounds):
   - 0–30%: green tint
   - 30–60%: amber tint
   - 60–80%: orange tint
   - 80–100%: red tint
3. Needle: line from center (100, 96) to angle proportional to value
4. Center dot: 5px black circle
5. Value text: 26px monospace above center
6. Band text: 10px uppercase below center
7. Label text: below the gauge
```

### 12.4 Waterfall (SHAP)

**Input:**
```javascript
{
  reasons: [
    { label: "Age of device", feature: "device_age_days", value: 18.97, contribution: 0.196 },
    { label: "High-risk location", feature: "is_high_risk_location", value: 1.0, contribution: 0.158 },
  ],
  protective: [
    { label: "Prior txn w/ merchant", feature: "customer_merchant_txn_count", value: 12.0, contribution: -1.444 },
    { label: "Digital footprint", feature: "digital_footprint_days", value: 5030.0, contribution: -0.852 },
  ],
  height: 300
}
```

**SVG rendering:**
```
1. Combine reasons (+sign) and protective (-sign) into one list
2. Compute max absolute contribution for scaling
3. Draw vertical baseline at x=430
4. For each row:
   a. Draw feature label (left-aligned, x=16)
   b. Draw bar:
      - If positive (risk): rect from baseline to right (red)
      - If negative (protective): rect from left to baseline (green)
   c. Draw contribution value (after bar, with +/- prefix)
   d. Draw raw feature value (far right, monospace)
5. Height scales with number of rows
```

### 12.5 DeltaBar

**Input:**
```javascript
{
  before: 0.2336,
  after: 0.1986,
  label: "Recall",
  format: (v) => pct(v, 1)
}
```

**SVG rendering:**
```
1. Calculate bar widths proportional to max(before, after)
2. Row 1: "Before" label + grey bar + value
3. Row 2: "After" label + green bar + value
4. Label "Recall" above both bars
```

### 12.6 StackedBar

**Input:**
```javascript
{
  segments: [
    { label: "LOW", value: 6025, colour: "#2dd4bf" },
    { label: "MEDIUM", value: 79, colour: "#fbbf24" },
    { label: "HIGH", value: 72, colour: "#fb923c" },
    { label: "CRITICAL", value: 32, colour: "#f2555a" },
  ]
}
```

**SVG rendering:**
```
1. Calculate total
2. For each segment: width = (value / total) × 700
3. Draw <rect> side by side, each with its colour
4. Below: legend with colour swatches and percentage labels
```

---

## 13. State Management

### Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                    App Mount                                 │
│                                                              │
│  useState("overview")  → initial page                       │
│  useState(null)        → run (no simulation yet)            │
│  useState(false)       → busy                               │
│  useState([])          → progress                           │
│  useState(null)        → simError                           │
│  useState("tiny")      → scale                              │
│  useState(null)        → detect                             │
│  useState(null)        → gap                                │
│  useState(null)        → loop                               │
│                                                              │
│  useEffect → GET /api/runs → adopt existing run if any      │
│  useHealth → GET /api/health → sidebar indicator             │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  User clicks "Run simulation"                               │
│                                                              │
│  setBusy(true)                                              │
│  setSimError(null)                                          │
│  setProgress([])                                            │
│  setDetect(null)  ← clears detection cache                  │
│  setGap(null)     ← clears gap cache                        │
│                                                              │
│  POST /api/simulate → job_id                                │
│  Poll /api/jobs/{id} → progress messages                    │
│  Job complete → setRun(result), setBusy(false)              │
│                                                              │
│  Auto: POST /api/detect → setDetect(result)                 │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  User navigates between pages                               │
│                                                              │
│  detect persists across Overview ↔ Blue Team ↔ Explain      │
│  gap persists across Gap ↔ Loop                             │
│  loop persists within Loop page                             │
│                                                              │
│  No refetch on page switch (cached in React state)          │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  User clicks "New simulation"                               │
│                                                              │
│  All caches cleared: detect=null, gap=null, loop=null       │
│  Process restarts from the top                               │
└─────────────────────────────────────────────────────────────┘
```

### Props Passed to Each Page

```javascript
shared = {
  run,          // Current simulation run object
  busy,         // Whether simulation is in progress
  simulate,     // Function to trigger a new simulation
  health,       // Backend health status
  detect,       // Detection results (cached)
  setDetect,    // Function to update detection cache
  gap,          // Gap analysis results (cached)
  setGap,       // Function to update gap cache
  loop,         // Adaptive loop results (cached)
  setLoop,      // Function to update loop cache
  goto: setPage // Function to navigate to a page
}

// Each page receives { ...shared, progress, simError }
```

### Why Caches Matter

Without caching, switching from Overview to Blue Team and back would:
1. Re-fetch detection results (wasteful — same data)
2. Show a loading skeleton on every switch (bad UX)
3. Potentially hit rate limits on the backend

With caching, page switches are instant — the data is already in React state.

---

## 14. Async Job Polling

### The Problem

Some operations (simulation build, adaptive loop) take 30 seconds to 15 minutes. A synchronous HTTP request would time out. Instead, the backend returns a job ID immediately and the work continues server-side.

### The Mechanism

```
1. Frontend: POST /api/simulate → {job_id: "abc123", status: "running"}
2. Frontend: starts polling loop
3. Every 1.5–2 seconds:
   Frontend: GET /api/jobs/abc123
   Backend:  {status: "running", progress: [{t: 1724000001, message: "Building population..."}]}
   Frontend: appends new messages to progress array
4. Eventually:
   Backend:  {status: "complete", result: {run_id: "xyz", summary: {...}}}
   Frontend: stops polling, stores result
5. Or on failure:
   Backend:  {status: "failed", error: "out of memory"}
   Frontend: stops polling, shows error
```

### Implementation in api.js

```javascript
export async function runJob(path, payload, onProgress, intervalMs = 1500) {
  // Step 1: Start the job
  const started = await post(path, payload);
  if (!started || !started.job_id) {
    return started;  // Synchronous endpoint — pass through
  }

  // Step 2: Poll until complete
  let seen = 0;
  for (;;) {
    await new Promise((r) => setTimeout(r, intervalMs));
    const job = await get(`/api/jobs/${started.job_id}`);
    const lines = (job && job.progress) || [];

    // Step 3: Surface new progress lines
    if (onProgress && lines.length > seen) {
      lines.slice(seen).forEach((l) => onProgress(l.message));
      seen = lines.length;
    }

    // Step 4: Check terminal states
    if (job.status === "complete") return job.result;
    if (job.status === "failed") throw new Error(job.error);
  }
}
```

### Progress Display

```javascript
// In the calling component:
const [progress, setProgress] = useState([]);

// runJob calls onProgress for each new line:
await runJob("/api/simulate", payload, (m) => setProgress((p) => [...p, m]));

// ProgressLog renders the growing array:
<ProgressLog lines={progress} running={busy} title="Building world" />
```

Each new message triggers a React state update, which re-renders the ProgressLog component with the new `<li>` appended. The log container has `max-height: 280px; overflow-y: auto` so it scrolls automatically.

---

## 15. Error, Loading, Empty States

### Three States for Every Data-Dependent Page

| State | Condition | What Renders |
|---|---|---|
| **Loading** | `loading === true` | Skeleton component (animated bars) |
| **Error** | `error !== null` | ErrorNote with error message + retry button |
| **Empty** | `data === null && !loading && !error` | EmptyState with title, description, action button |
| **Loaded** | `data !== null` | Full content |

### How Each Page Manages States

```javascript
// Generic pattern used in Overview, Blue Team, Gap Analysis:
const [data, setData] = useState(null);
const [loading, setLoading] = useState(false);
const [error, setError] = useState(null);

const load = useCallback(async () => {
  setLoading(true);
  setError(null);
  try {
    const result = await post("/api/endpoint", { run_id: run.run_id });
    setData(result);       // or setDetect(result) for shared state
  } catch (e) {
    setError(e);
  } finally {
    setLoading(false);
  }
}, [run]);

// Auto-load on mount:
useEffect(() => {
  if (run && run.run_id && !data) load();
}, [run, data, load]);
```

### Retry Mechanism

Every ErrorNote has an optional retry button:

```jsx
<ErrorNote error={error} onRetry={load} />
// Renders: "Try again" button that calls load() again
```

### Auto-Loading with Guards

The `useEffect` guard prevents duplicate fetches:

```javascript
useEffect(() => {
  if (run && run.run_id && !detect) load();
  //                ^^^^^^^^^^^^
  // Only fetch if:
  // 1. A run exists
  // 2. Detection hasn't been fetched yet
}, [run, detect, load]);
```

---

## 16. Responsive Breakpoints

### Three Breakpoints

```css
/* Desktop (default): sidebar 260px, main flex */
/* Tablet: sidebar 210px, narrower padding */
@media (max-width: 1180px) {
  .sidebar { width: 210px; flex-basis: 210px; }
  .main { padding: 18px 20px 50px; }
  .grid-3, .intel-grid { grid-template-columns: 1fr; }
  .ba { grid-template-columns: 1fr; }
  .ba-arrow { transform: rotate(90deg); }
  .runbar { flex-wrap: wrap; }
  .runbar-stats { margin-left: 0; flex-basis: 100%; }
}

/* Mobile: sidebar on top, full width */
@media (max-width: 860px) {
  .shell { flex-direction: column; }
  .sidebar { width: 100%; flex-basis: auto; height: auto; position: static; }
  .grid-2, .grid-4 { grid-template-columns: 1fr; }
  .topbar { flex-direction: column; }
}
```

### 4-Column Grid Collapse

```css
/* Default: 4 columns */
.grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }

/* Below 1400px: 2 columns */
@media (max-width: 1400px) {
  .grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

/* Below 860px: 1 column */
@media (max-width: 860px) {
  .grid-2, .grid-4 { grid-template-columns: 1fr; }
}
```

---

## 17. Proxy Configuration

### next.config.js

```javascript
module.exports = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",          // Match any /api/* request
        destination: "http://localhost:8000/api/:path*",  // Forward to backend
      },
    ];
  },
};
```

### How It Works

1. Frontend code calls `fetch("/api/health")`
2. Browser sends request to `http://localhost:3000/api/health` (same origin)
3. Next.js dev server intercepts the request
4. Next.js forwards it to `http://localhost:8000/api/health`
5. Python backend processes and returns JSON
6. Next.js relays the response back to the browser

### Why This Pattern?

- **No CORS issues:** Browser sees everything as same-origin (port 3000)
- **No hardcoded ports in frontend code:** Just use `/api/*` paths
- **Production-ready:** In production, Next.js serves static files and the backend can be behind a reverse proxy
- **Environment override:** The `SG_API_URL` environment variable can override the backend URL

### Custom Override

If the backend runs on a different host/port, set `SG_API_URL`:

```bash
SG_API_URL=http://192.168.1.100:8000 npm run dev
```

The next.config.js reads this variable and adjusts the proxy destination.
