# SovereignGuard — Software Design Document (SDD)

|     | |
| --- | --- |
| **Product** | SovereignGuard — AI Red Team / Blue Team Payment-Fraud Testing Lab |
| **Version** | 1.0 |
| **Date** | 2026-08-30 |
| **Status** | As-built (reflects current implementation) |
| **Applies to** | v1.0 SRS (`docs/SRS.md`), PRD (`docs/PRD.md`) |

---

## 1. Introduction

### 1.1 Purpose
Describe the architecture, module design, algorithms, data contracts, concurrency
model and deployment of SovereignGuard as implemented. This document is a map to
the code: every section lists the source files it describes.

### 1.2 System overview
SovereignGuard is a two-process lab:

1. **Python core** (~7.8 k LOC): deterministic synthetic data engine, red team,
   from-scratch ML (histogram GBDT / random forest / TreeSHAP), risk decision
   layer, gap analysis, adaptive loop, SQLite store, snapshot persistence and a
   dependency-free `http.server` REST API with async jobs + SSE.
2. **Next.js 14 dashboard**: a 9-view responsive console that proxies `/api/*`
   to the Python API and subscribes to named SSE events.

Design pillars: **no label leakage**, **structural causality**, **determinism**,
**no third-party ML**, and **humble numbers** (the adaptive loop guards against
memorisation by design).

---

## 2. Architecture goals & constraints

| Goal | How it is achieved |
| --- | --- |
| Causality is structural, not best-effort | Features emitted before a transaction is appended to history (`features.py` streaming pass); truncation test proves bit-identical output |
| No leakage | `FEATURE_COLUMNS` / `LABEL_COLUMNS` disjoint contract in `schema.py` + `assert_no_leakage()` audit |
| Deterministic & reproducible | A single `SEED` + `RunConfig` fingerprint; identical simulate requests serve a cached world |
| Dependency-free ML | All models implemented in numpy; verified against definitions, not libraries |
| Honest adaptive results | Two independent adversarial batches (train vs never-seen eval) from different RNG streams |
| Fast reboot | Snapshot (world pickle + detector JSON) restores a trained lab in seconds |
| Long ops never block UI | Every slow endpoint returns `202 {job_id}` immediately; progress via poll/SSE |

---

## 3. System architecture

```
                           ┌────────────────────────────────────────────┐
                           │ Next.js dashboard (:3000)                  │
                           │  pages/index.jsx · views/ ×9 · components/ │
                           │  lib/api.js (get/post/runRealtime)         │
                           └────────────────────────────────────────────┘
                                       │  /api/* rewrite → SG_API_URL
                                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Python API  sovereignguard/api/server.py (http.server, :8000)        │
│  AppState: worlds, detectors, jobs, memo, world_cache, store         │
│  ROUTES_GET / ROUTES_POST / prefix routes (/api/sse, /api/jobs, ...) │
└───────┬─────────────────────────────┬────────────────────────┬────────┘
        │                             │                        │
        ▼                             ▼                        ▼
┌───────────────┐      ┌──────────────────────┐     ┌───────────────────┐
│ pipeline.py   │      │ store.py (SQLite)    │     │ snapshot.py       │
│ build_world   │      │ runs/models/risk/    │     │ world.pkl +       │
│ train_baseline│      │ attacks/gaps/loops   │     │ detector/ + meta  │
│ adversarial_  │      │ experiments          │     │ (boot seeding)    │
│ loop          │      └──────────────────────┘     └───────────────────┘
│               │
└───┬───────┬──────────┬───────────────┬───────────────┬──────────────┐
    ▼       ▼          ▼               ▼               ▼              ▼
 generators  features.py  detection.py   risk.py    evaluation/      ml/
 population   (83 causal   Detector·     bands→      metrics.py      tree.py
 transactions  features,   splits·       actions    gap_analysis.py  models.py
 attacks       no leak)    explain                               treeshap.py
 families
 redteam
 adversarial
```

### 3.1 Module inventory

| Module | LOC | Responsibility |
| --- | --- | --- |
| `sovereignguard/config.py` | 382 | All tunables: scales, personas, categories, cities, risk bands, event rates, paths |
| `sovereignguard/rng.py` | 68 | Task-seeded RNG streams (independent streams per campaign) |
| `sovereignguard/schema.py` | 275 | Canonical column contracts + feature labels + leakage guard |
| `sovereignguard/features.py` | 522 | 83 causal features, streaming per-customer pass |
| `sovereignguard/generators/` | ~2 k | population, transactions, attacks, families (playbooks), redteam, adversarial |
| `sovereignguard/ml/` | ~920 | `tree.py` (Binner/Tree/TreeBuilder), `models.py` (GBDT/RF), `treeshap.py` |
| `sovereignguard/detection.py` | 380 | Splits, `Detector`, `train_detector`, explain, save/load |
| `sovereignguard/risk.py` | 144 | Probability → risk score → band → action |
| `sovereignguard/evaluation/` | ~660 | `metrics.py`, `gap_analysis.py` (10 hypotheses) |
| `sovereignguard/taxonomy.py` | 100 | Loader for the 7-family attack knowledge base |
| `sovereignguard/snapshot.py` | 80 | World+detector persistence for fast boot |
| `sovereignguard/store.py` | 408 | SQLite persistence + optional Postgres DDL |
| `sovereignguard/api/server.py` | 1237 | REST, async jobs, SSE, static dashboard |
| `sovereignguard/pipeline.py` | 505 | `build_world`, `train_baseline`, `adversarial_loop`, `World` |
| `frontend/pages/index.jsx` | 243 | Shell, nav (9 views), shared run state, SSE client wiring |
| `frontend/views/` ×9 | — | Per-surface UI |
| `frontend/components/` | — | `UI.jsx`, `Charts.jsx` (dependency-free SVG/CSS charts) |
| `frontend/lib/api.js` | 233 | HTTP helpers + `runRealtime` SSE + formatters |
| `sg.py` | — | CLI dispatch to pipeline commands |
| `verify.py` | 1037 | 14 assertive end-to-end stages |

---

## 4. Data design

### 4.1 Column contracts (schema.py)
- `EVENT_COLUMNS` (26): the raw stream a payment switch would emit — ids,
  timestamp (unix s), amount, method, channel, type, device, geo, beneficiary,
  auth result, MCC, session/account context flags.
- `LABEL_COLUMNS` (7): `fraud_label`, `attack_type`, `attack_id`, `attack_stage`,
  `difficulty`, `generator`, `campaign_id` — **never features** (asserted).
- `FEATURE_COLUMNS` (83) grouped: amount (9), velocity (13), device (7),
  location (6), merchant (8), temporal (6), account/identity (6), session/auth
  (12), method/channel/type one-hots (12), sequence/graph (4).
  Every feature has a human label; the mapping is enforced at import.
- Entity frames: `CUSTOMER_COLUMNS`, `MERCHANT_COLUMNS`, `DEVICE_COLUMNS`.

### 4.2 Transaction representation
`TRANSACTION_COLUMNS = EVENT_COLUMNS + LABEL_COLUMNS`. Features are *derived*;
the model trains on `feats[FEATURE_COLUMNS]` only. `World` bundles `tx`, `feats`,
`customers`, `merchants`, `devices`, `legit_tx`, `batch`, `red_team`, `config`.

### 4.3 Store (SQLite)
Tables (via `Store._init_schema`): runs, model_runs, txn_risk_scores,
attack_results, gap_reports, loop_results, experiments. All mutations
run in-process under `AppState`'s `RLock`. The DB deliberately lives outside the
repo dir (`~/.local/state/sovereignguard/sovereignguard.db`, `SG_DB_PATH`
override) to avoid network-mount POSIX-locking failures. `postgres_ddl()` emits a
Postgres equivalent for scale-out experiments.

### 4.4 Snapshot
`data/snapshot/` holds `world.pkl` (World dataclass), `detector/`
(`detector.json` meta + `model.json.gz` trees) and `meta.json`. On boot,
`seed_snapshot` restores the world+detector and pre-warms `world_cache` with the
snapshot's own config fingerprint, so the first identical "New simulation" is
instant.

### 4.5 Experiments
`experiments/run_all.py` runs six measured studies and persists JSON to
`experiments/results/`, each artefact carrying raw numbers + an environment
fingerprint: `exp1_baseline`, `exp2_diversity`, `exp3_unseen`, `exp4_adversarial`,
`exp5_adaptive`, `exp6_false_positives`.

---

## 5. Component design

### 5.1 Config & RNG
- `ScaleProfile`: `n_customers`, `n_merchants`, `n_days`, `attacks_per_type`;
  five profiles (`nano` 300/21d → `full` 100k/90d). `RunConfig` bundles scale,
  seed, attack mix, difficulty mix (EASY 0.25 / MEDIUM 0.40 / HARD 0.35) and
  `target_fpr`.
- `Persona` (×7) drives all legitimate behaviour: lognormal amounts, per-persona
  method/category affinities, night activity, travel, new-merchant and
  device-change rates, transfer share. `CategorySpec` (×14) defines ticket
  distributions, intrinsic risk, CNP share and peak hours. Cities (×20) carry
  lat/lon + population weight; 4 are flagged high-risk for attackers.
- `rng.py` derives deterministic sub-streams so campaigns never depend on global
  RNG order.

### 5.2 Generators
| File | Design |
| --- | --- |
| `population.py` | Build customers/merchants/devices from personas, categories and cities; assigns KYC, identity-doc and contactability scores |
| `transactions.py` | Emits the legitimate stream: per-customer inter-arrival + amount + method + category, hour-of-day rhythms, life events |
| `attacks.py` | Phase a campaign script: pre-processing (credential/device prep) then execution (drain/purchase/transfer), each event produced with attack-consistent techniques |
| `families.py` | 7 family playbooks mapping taxonomy stages onto concrete generators and evasion knobs (533 LOC) |
| `redteam.py` | `RedTeam` + `AttackBatch` + `merge_world`: re-mints ids, splices scenarios, recomputes features; `diversity_report()` |
| `adversarial.py` | `AdversarialGenerator`: produces TWO independent batches from identical params, different RNG streams (`adv_train` to retrain, `adv_eval` for reporting) |

`merge_world` re-sorts the combined stream by `(timestamp, transaction_id)` and
re-derives all features so injected events inherit genuine history context.

### 5.3 Features
One streaming pass per customer (append *after* emitting) plus one global pass
for cross-account graph features (`customer_risk_events_24h`,
`beneficiary_indegree_24h`, `merchant_new_customer_share_24h`). Windows are
fixed constants (\(W_{10m}, W_{1h}, W_{24h}, W_{7d}, W_{30d}\)). Haver sine
distances feed geo-velocity; round-number and structuring heuristics feed
`amount_round_number`. `assert_no_leakage()` re-checks the contract post-build.

### 5.4 ML core
- **`tree.py`** — `Binner` quantilises features to uint8 codes (≤64 bins, bin 0
  reserved for missing) fitted on training data only. `TreeBuilder` picks splits
  from gradient/hessian histograms; the larger child's histogram is derived by
  subtraction from the parent (only the smaller child scanned). The second-order
  gain reduces to variance reduction when grad=`-y`, hess=`1`, so **one builder
  serves GBDT and Gini-equivalent RF splits**.
- **`models.py`** — `GradientBoostingClassifier` (n_estimators 300, lr 0.10,
  max_depth 6, max_leaves 63, min_samples_leaf 25, l2 1.0, subsample 0.8,
  colsample 0.7, early stopping 30) and `RandomForestClassifier` (120 trees,
  depth 14, colsample 0.35, class-weight balanced), plus `logloss`/`sigmoid`.
  `BaseModel.save/load` → `model.json.gz`.
- **`treeshap.py`** — path-dependent TreeSHAP (Lundberg, Erion & Lee), O(T·L·D²)
  via `_tree_shap_single` extend/unwind recursion. **Local accuracy is asserted:
  `base + Σφ == model output`.** Verified by brute-force Shapley evaluation on
  small trees (`tests/test_ml.py::test_treeshap_matches_brute_force_shapley`).

### 5.5 Detection
- **Splits.** `temporal_grouped_split`: time-ordered train 60% / valid 15% /
  test 25%, with whole campaigns assigned by majority bucket.
  `unseen_attack_split`: held-out families exist in test only; test also retains
  late seen-families as a same-threshold reference (keeps recall numbers
  interpretable).
- **`train_detector`** — fits the model, picks the threshold on **validation**
  via `choose_threshold_at_fpr` (highest recall within budget, default 1 %;
  prevalence fallback if valid is empty), evaluates on test with per-group break-
  downs, records top-20 importance, fit time, split sizes and tree counts in
  `train_meta`.
- **`Detector`** — `predict_proba`, `decide` (probability/score/band/action/flag),
  `evaluate` (metrics + operating curve + risk distribution + friction + group
  metrics + latency), `explain` (TreeSHAP → reasons / protective factors),
  `save/load`. A `MODEL_REGISTRY` maps `gbdt`/`forest`. `optional_backends()`
  reports importability of xgboost/lightgbm/sklearn/shap for cross-checks without
  depending on them.

### 5.6 Risk layer
`RiskEngine` maps probability → a 0–100 risk score with the detector's operating
threshold **pinned to the STEP_UP band edge** (piecewise-linear above/below), so
policy bands stay aligned with model calibration across retrains. Bands → actions:
LOW→ALLOW (0–30), MEDIUM→MONITOR (30–60), HIGH→STEP_UP_AUTH (60–80),
CRITICAL→HOLD_REVIEW (80–100). Provides `distribution` (band × legit/fraud)
and `friction_summary` (challenged share of honest traffic, stopped share of
fraud) — the "is the policy doing useful work" view.

### 5.7 Evaluation
- **`metrics.py`** — `roc_auc`, PR curve, `average_precision`, `Metrics`,
  `choose_threshold_at_fpr` / `_max_f1`, `operating_curve`, `per_group_metrics`,
  `compare_models`, `bootstrap_ci`.
- **`gap_analysis.py`** — 10 `Hypothesis` rows; each has a *feature predicate*
  evaluated on the missed segment vs calibrated quantiles of legitimate traffic,
  an `exploit_knob` (the generator parameter an attacker tweaks) and a
  `remediation`. `analyse_gaps` scores propensity by hypothesis and describes the
  missed segment; `compare_gap_reports` measures shrink after the loop.

### 5.8 Pipeline
- `build_world(scale, seed, …)` — population → legitimate stream → baseline
  attack batch → features → `World`. Deterministic.
- `train_baseline(world, …)` — temporal split → `train_detector`.
- `adversarial_loop(world, det, …)` — debug (`diagnose`) → generate two
  adversarial batches → retrain on `adv_train` → retest on **`adv_eval` only**,
  both models at the same FPR budget → persisted loop report.

### 5.9 API server
- **Routing.** `ROUTES_GET` (8), `ROUTES_POST` (9), plus prefix-dispatched
  parameterised routes (`/api/taxonomy/{type}`, `/api/runs/{id}`,
  `/api/sse/{id}`, `/api/jobs/{id}`, `/api/experiments/{id}`). Anything outside
  an explicit rewrite reaches the handlers raw; unknown `/api/*` returns 404 with
  the route list.
- **`AppState`** (singleton) — holds `store`, warm `worlds`, `detectors`, `jobs`,
  `default_run`, `baseline`, `world_cache` (config fingerprint → World) and a TTL
  `memo` for detect/gap, all protected by `RLock`.
- **Async jobs.** `start_job(kind, fn, feed)` spawns a daemon thread and returns
  `job_<10 hex>`. Long handlers return `202 {job_id, status:"running"}`. Job
  records carry `status`, progress `notes`, `result` or `error`+`traceback`.
  `/api/sse/{id}` streams named `generation`/`progress`/`done`/`error` events
  with a 12 s `: beat`.
- **Errors & disconnects.** `_send`/`_send_file` swallow
  `BrokenPipeError`/`ConnectionResetError`/`TimeoutError`; `SGServer.handle_error`
  silences them — **clean logs are the expected state**, and this must not be
  "fixed" by printing tracebacks.

### 5.10 Frontend
- **Shell** (`pages/index.jsx`): shared `run` state lifted to the app root;
  `useHealth` polls `/api/health`; `simulate()` uses `runRealtime` (SSE client)
  wiring `generation`/`progress`/`done`/`error` to UI state. Nav groups
  Situation / Red Team / Blue Team / Adaptive.
- **Views** (`views/`): Overview, Live Monitor (4 s poll + live event stream),
  Attack Intelligence, Red Team Simulator (async generate), Attack Studio
  (scenario anatomy + victim timeline), Blue Team Detection, Explainability
  (search → score → TreeSHAP waterfall), Gap Analysis, Adaptive Loop (hero).
- **Components**: `UI.jsx` (Card, Table, Kpi, Badge, ProgressLog, Skeleton,
  ErrorNote, EmptyState), `Charts.jsx` (dependency-free SVG + CSS charts:
  Gauge, Waterfall, BarChart, DeltaBar, StackedBar, AttackTimeline, StagePipeline,
  EntropyBar, LineChart). The SHAP waterfall is DOM/CSS (not SVG-scaling text) so
  it stays readable at mobile widths; bars diverge from a centre axis and the
  breakpoint ≤640 px stacks each row.
- **`lib/api.js`**: `post`/`get` normalise JSON errors (throw on malformed body),
  `runRealtime` resolves the job to its result and settles once; formatters
  `num/pct/int/money/shortAttack/bandClass`.

### 5.11 CLI (`sg.py`)
Subcommands: `build`, `train`, `redteam`, `gap`, `loop`, `demo`, `experiments`,
`snapshot`, `serve` (honours `SG_SEED=0` for an empty lab), `taxonomy`.

---

## 6. Key algorithms

| Algorithm | Design | Where |
| --- | --- | --- |
| Histogram split gain | \(G_L^2/(H_L+\lambda)+G_R^2/(H_R+\lambda)-G^2/(H+\lambda)\); histogram-of-small-child via parent subtraction; `grad=-y, hess=1` ⇒ variance/Gini-equivalent | `ml/tree.py` |
| Quantile binning | ≤64 bins per feature; missing→bin 0; fitted on train only | `ml/tree.py:Binner` |
| Threshold selection | Highest recall with FPR ≤ budget on validation via sorted-score scan | `metrics.choose_threshold_at_fpr` |
| TreeSHAP | O(T·L·D²) extend/unwind; asserted local accuracy; brute-force cross-checked | `ml/treeshap.py` |
| Temporal+grouped split | Time cut + whole-campaign reassignment by majority bucket | `detection.temporal_grouped_split` |
| Risk mapping | Piecewise-linear probability→score anchored at STEP_UP edge; band via searchsorted | `risk.py` |
| Gap hypotheses | Candidate predicate on missed-fraud vs calibrated legit quantiles | `evaluation/gap_analysis.py` |
| World fingerprint | Deterministic JSON of config → `world_cache` hit | `server.py` / `snapshot.py` |
| RNG streams | Independent deterministic sub-streams per task/campaign | `rng.py` |

---

## 7. Concurrency & process model

- One Python process; `AppState` under `RLock`.
- Long work (`simulate`, `redteam generate`, `loop`) runs in daemon worker
  threads; the HTTP thread returns `202` immediately.
- Clients **poll** `/api/jobs/{id}` or **subscribe** to `/api/sse/{id}`.
  SSE writers walk the job's `feed` by per-client offset; keepalive `: beat`.
- Expensive pure reads (detect, gap) are memoised per `(kind, run, detkey)` with
  a 600 s TTL; identical simulate requests hit the fingerprint world cache.
- Next dev server proxies `/api/*`; the frontend keeps cross-page result caches
  (`detect`, `gap`, `loop`) so tab switches avoid refetching.

---

## 8. Error handling

| Layer | Policy |
| --- | --- |
| API | JSON `{error}` with HTTP status (400/404/500); unknown `/api/*` returns the route list |
| Jobs | Failure recorded as `error` + `traceback` in the job record; SSE emits named `error` |
| Client disconnect | Silently swallowed (`BrokenPipeError`, `ConnectionResetError`, `TimeoutError`) — normal |
| Frontend | `post/get` throw on malformed/error responses; views render `ErrorNote` and recover |
| ML | Contract asserts (`assert_no_leakage`, local accuracy, missing-feature guard) fail loudly at build/train |

---

## 9. Deployment

| Path | Steps |
| --- | --- |
| Local | `python sg.py snapshot --scale demo` then `python sg.py serve`; frontend `cd frontend && npm install && npm run dev` |
| Everything at once | `./boot.sh` |
| Docker | `docker compose up backend` (API :8000), `docker compose up` (+ dashboard), `docker compose run --rm demo`, `… --rm experiments` |
| Environment | `SG_API_URL` (frontend→API), `SG_HOST`/`SG_PORT` (bind), `SG_SEED=0` (no seed), `SG_DB_PATH`/`SG_STATE_DIR` (state), `SG_DATA_DIR`/`SG_MODELS_DIR`/`SG_EXPERIMENTS_DIR` (artefacts), `SG_SCALE`/`SG_TARGET_FPR` (defaults) |

---

## 10. Verification strategy

| Concern | Mechanism |
| --- | --- |
| Correctness of ML | Numeric unit tests (`test_ml.py`) + TreeSHAP brute-force cross-check |
| Leakage / causality / campaigns | `test_leakage_audit.py`, `test_features.py`, split tests |
| API contract | Hermetic temp-store tests (`test_detection_api.py`) — never fight a live server's sqlite |
| Whole pipeline | `verify.py` — 14 assertive stages (`env tests world redteam blueteam explain risk gap loop audit api store cli frontend`), `--quick`/`--full` profiles |
| Frontend | `npm run build` + static import/export stage + headless browser smoke tests (no console errors) at desktop/tablet/mobile widths |

Current evidence: **92/92 tests**, **14/14 verify stages**, clean `npm run build`,
clean browser console.

---

## 11. Trade-offs & known limits

- **Pure-Python streaming features** (~60–100 k rows/s) prioritise auditability
  over borrowed pandas-rolling speed.
- **SQLite + pickle snapshots** prioritise fast lab reboot over bank-grade
  persistence; `postgres_ddl()` is the escape hatch.
- **`nano`/`tiny` scales** give wide confidence intervals by design → load-bearing
  results require `demo`.
- **Frontend is smoke-tested, not unit-tested**; a UI test harness is future work.
- Risk bands and thresholds are **prototype policy**, intentionally tunable and
  never claimed to be any real scheme's values.

---

## 12. Version history

| Version | Date | Change |
| --- | --- | --- |
| 1.0 | 2026-08-30 | Initial as-built SDD; documents async job + SSE model, snapshot reboot path, cleared-run fallback, responsive waterfall, memoisation and fingerprint caching. |