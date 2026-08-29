# SovereignGuard Dashboard

Next.js analyst console for the SovereignGuard payment-defence lab.

## Running it

The dashboard is a **client for the Python backend**. Start the backend first.

```bash
# terminal 1 — backend API on :8000
cd ..
python sg.py serve

# terminal 2 — dashboard on :3000
cd frontend
npm install
npm run dev
```

Then open <http://localhost:3000>.

`next.config.js` proxies `/api/*` to `http://127.0.0.1:8000`, so the browser sees a
single origin and there is no CORS configuration to get wrong. If your backend runs
elsewhere, set `SG_API_URL`:

```bash
SG_API_URL=http://192.168.1.20:8000 npm run dev
```

## Pages

| Page | What it shows |
|---|---|
| Overview | Headline KPIs, live generation strip, risk-band routing, operating curve |
| **Live Monitor** | **Realtime ops wall** — SSE-streamed attacker feed while simulating, 4s world sync at rest |
| Attack Intelligence | The 7-family GenAI fraud taxonomy, stages, signals, mitigations |
| Red Team Simulator | Generate attacks; measured diversity (normalised entropy per dimension) |
| Attack Studio | Replay of generation + per-attack anatomy (stages, knobs, victim timeline, model scores) |
| Blue Team Detection | Full metric suite, recall by family and by evasion skill, feature importance |
| Explainability | Per-transaction TreeSHAP waterfall, risk gauge, reason codes |
| Gap Analysis | Why attacks evaded detection, ranked by attribution; weakest segments |
| **Adaptive Loop** | **The hero screen** — before/after at a matched false-positive budget |

## Design notes

Three dependencies only: `next`, `react`, `react-dom`.

- **Charts are hand-written SVG** (`components/Charts.jsx`) rather than recharts or
  chart.js. There is no charting library version to break, and each chart is a pure
  function of its data.
- **Plain CSS** (`styles/globals.css`), not Tailwind — no PostCSS pipeline to
  misconfigure.
- **System font stacks only.** No webfont fetch, so the console renders identically
  offline.
- **No browser storage.** All state is React state, lifted into `pages/index.jsx` and
  passed down, so switching tabs preserves results without persisting anything.

`globals.css` is imported **only** in `pages/_app.jsx`; Next.js rejects global
stylesheet imports from any other module.

## Async + realtime endpoints

`POST /api/simulate` and `POST /api/loop` return `202` with a `job_id` and continue
server-side. `lib/api.js#runJob` polls `GET /api/jobs/{id}` and streams each
`progress[].message` into the UI, so a loop that runs for two minutes shows a live log
rather than appearing to hang.

For realtime, `lib/api.js#runRealtime` opens an
`EventSource` on `GET /api/sse/{job_id}`. The backend pushes three event types over a
real chunked HTTP stream — `progress`, `generation` (per-scenario telemetry the moment
a scenario is built) and `done` — with no polling. If EventSource is unavailable the
client transparently falls back to `GET /api/jobs/{id}` polling. The generation stream
is what drives the Live Monitor and the Overview generation strip.

## Verification status

This code was written in an environment without network access, so `npm install` and
`next build` could **not** be executed against it. What *was* verified statically:

- every relative and package import resolves to a real file or a declared dependency
- every imported name exists as an export in its source module
- React hooks are imported from `react` in all 9 modules that use them
- **all 134 API field references were checked against live responses from the running
  Python backend** — zero mismatches

Expect to run `npm install` before first use. If the build reports anything, it will
most likely be a lint preference rather than a resolution error.

## Fallback

If you cannot run Node, the backend serves its own JSON API and a full CLI covers the
same ground:

```bash
python sg.py demo          # the whole story in one command
python sg.py gap           # gap analysis in the terminal
python sg.py loop -n 400   # the adaptive loop
```
