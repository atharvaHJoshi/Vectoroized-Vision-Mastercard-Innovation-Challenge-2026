# SovereignGuard — Software Requirements Specification (SRS)

|     | |
| --- | --- |
| **Product** | SovereignGuard — AI Red Team / Blue Team Payment-Fraud Testing Lab |
| **Version** | 1.0 |
| **Date** | 2026-08-30 |
| **Status** | Implemented — this document specifies the *as-built* system |
| **Companion docs** | `docs/PRD.md` (product), `docs/SDD.md` (design), `README.md`, `DOCUMENTATION.md`, `UI_DOCUMENTATION.md` |

---

## 1. Introduction

### 1.1 Purpose
Specify the functional, interface, non-functional and data requirements of the
SovereignGuard payment-fraud testing laboratory. This SRS reflects the **current
implemented status** of the system and is the contract against which tests,
verification stages and UI behaviour are read.

### 1.2 Scope
In scope: the deterministic synthetic-world generator; the red-team campaign
generator; the from-scratch ML detector (histogram GBDT / random forest /
TreeSHAP); the risk decision layer; gap analysis with ten evasion hypotheses; the
adaptive attack/defence loop; the REST API with async job + SSE model; the SQLite
store and snapshot reboot path; the responsive Next.js dashboard; the CLI; and
the end-to-end verification harness.

Out of scope: real payment data, real-time production fraud decisioning, renewal
with third-party ML frameworks, and UI-automation test suites.

### 1.3 Definitions & acronyms
| Term | Meaning |
| --- | --- |
| World | A built synthetic population + transaction stream + fraud inject + red team |
| Run | A persisted simulate pipeline execution (with its DB record) |
| Scenario / campaign | One `attack_id`: a time-resolved multi-stage fraud attempt |
| Detector | Trained Blue Team model + operating threshold + risk policy + metrics |
| FPR budget | False-positive-rate cap used to choose the threshold on validation |
| FEATURE_COLUMNS | The 83 columns a model may see |
| LABEL_COLUMNS | Columns (`fraud_label`, `attack_type`, `attack_id`, …) that must never be features |
| SSE | Server-Sent Events, the streaming channel for job progress |
| Persona | One of 7 behavioural profiles driving legitimate behaviour |

### 1.4 References
IEEE 830-1998 (structure), `AGENTS.md` (project conventions & gotchas),
`DOCUMENTATION.md` (API reference), `UI_DOCUMENTATION.md` (frontend),
`frontend/README.md`, `verify.py` (stage definitions), `tests/` (suite).

---

## 2. Overall description

### 2.1 Product perspective
SovereignGuard is a standalone, self-contained lab. It has no external data
dependencies: path configuration points at local directories, the ML runtime is
numpy/pandas only, and the frontend is served by Next.js proxying `/api/*` to the
Python `http.server`-based API.

```
┌──────────────┐   /api/*  rewrite   ┌──────────────────────────┐
│ Browser      │ ──────────────────► │ Next.js dashboard (:3000)│
│ (responsive) │                     └──────────────────────────┘
└──────────────┘                                  │
    ▲                                              │  SG_API_URL (default
    │ SSE events / REST                           │  http://127.0.0.1:8000)
    └──────────────────────────────────────────────▼
                                   ┌──────────────────────────┐
                                   │ Python API + pipeline    │
                                   │ (http.server, :8000)     │
                                   │ worlds · detectors · jobs│
                                   └───────┬──────────┬───────┘
                                           │          │
                                  SQLite store  data/snapshot (pickle)
                                  (~/.local/state)  world + detector
```

### 2.2 Operating environment
| Concern | Requirement |
| --- | --- |
| Python | ≥ 3.10 (uses `X | None` type syntax, `dict` membership typing) |
| ML runtime | numpy + pandas only (no XGBoost/LightGBM/sklearn required) |
| Frontend | Node.js + Next.js 14 (plain JS/JSX) |
| OS | Linux/macOS/Windows-WSL; SQLite requires POSIX file locking (see §5.1) |
| Browser | Modern evergreen (dark-theme console; no network fonts) |
| Docker | Orchestration via `docker-compose.yml` (backend / backend+dashboard / demo / experiments) |

### 2.3 Design constraints & conventions
- **Causality is structural.** Features for a transaction may use only data
  strictly before it (plus static account/merchant/device attributes).
- **No label leakage.** `FEATURE_COLUMNS ∩ LABEL_COLUMNS = ∅`, enforced and audited.
- **Determinism.** All runs derive from `SEED` (default `20260823`) + a config
  fingerprint; identical simulate requests short-circuit to the cached world.
- **No third-party ML.** Every algorithm is implemented and verified in-repo.
- **Dependency-free API.** The REST server is Python's standard `http.server`.
- **Prototype thresholds.** Risk bands are tunable policy prototypes, not a real
  scheme's values, and are labelled as such in the UI/API.

### 2.4 User characteristics
Analysts, red-teamers and security officers with desktop browsers; one operator
per lab instance (single-process backend; job concurrency is internal).

### 2.5 Assumptions & dependencies
- A default snapshot may not exist on first boot; `serve` without `SG_SEED=0`
  seeds automatically when present and otherwise boots empty.
- Next dev proxy aborts upstream requests idle past ~30 s, so all long operations
  must respond immediately via the async job contract (§3.2) or SSE.

---

## 3. Specific requirements

### 3.1 External interface requirements

**User interfaces (dashboard).** Nine views plus the shared run banner and scale
picker:

| View | Route id | Purpose |
| --- | --- | --- |
| Overview | `overview` | Hero loop, world summary, health |
| Live Monitor | `live` | 4 s-poll event stream of the active world |
| Attack Intelligence | `intel` | Taxonomy + per-family playbooks |
| Red Team Simulator | `redteam` | Generate N campaigns (async), watch progress |
| Attack Studio | `studio` | Scenario picker + anatomy playback |
| Blue Team Detection | `blueteam` | Metrics, risk distribution, per-family recall |
| Explainability | `explain` | Search/scored transactions + SHAP waterfall + reason tables |
| Gap Analysis | `gap` | 10 evasion hypotheses + hypothesis scores |
| Adaptive Loop | `loop` | Diagnose → adapt → retrain → retest report |

Requirements: the console must be responsive down to mobile widths
(verified at 390–1440 px); tables scroll horizontally rather than breaking
layout; all styling must come from a single `globals.css` imported only in
`pages/_app.jsx`.

**Communications interfaces.**

| Requirement | Detail |
| --- | --- |
| REST | JSON; `http.server` at `127.0.0.1:8000` (env: `SG_HOST`/`SG_PORT`) |
| Streams | `GET /api/sse/{job_id}` emits named `progress` / `generation` / `done` / `error` events (12 s keepalive) |
| Proxy | Next rewrites `/api/*` → `SG_API_URL` (default `http://127.0.0.1:8000`) |
| CORS | Wildcard `Access-Control-Allow-Origin` + `OPTIONS` preflight (bypassed by the dev rewrite) |

### 3.2 Functional requirements

Each requirement is numbered, states the observable behaviour, and is verified by
a test or verification stage (found in `tests/` or `verify.py`).

#### A. Identity & knowledge base
| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-A1 | Expose a 7-family attack taxonomy with severity, base-rate prior, stages and evasion playbook; with per-family retrieval. | `tests/test_schema.py` (taxonomy validation), API `/api/taxonomy`, `/api/taxonomy/{type}` |
| FR-A2 | New attack generations must draw on the taxonomy's evasion knobs by family. | `tests/test_generators.py` |

#### B. World generation
| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-B1 | Build a deterministic world from (scale, seed, attack mix, difficulty mix, prevalence) so identical configs produce identical data. | `tests/test_generators.py` (attack spread), `/api/simulate` fingerprint cache |
| FR-B2 | Generate a population of 7 personas with per-persona age, amount (lognormal), method/category affinity, activity and life-event rates. | `tests/test_generators.py` |
| FR-B3 | Generate 14 merchant categories, 20 cities (+2 high-risk offshore), 4 methods, 4 channels and 4 transaction types. | `tests/test_generators.py`, `config.py` |
| FR-B4 | Emit the raw event stream with all `EVENT_COLUMNS` and labels, at the requested scale (`nano` 300 → `full` 100,000 customers). | `tests/test_generators.py` + `tests/test_features.py` |
| FR-B5 | Inject legitimately-suspicious behaviour (new devices, beneficiaries, travel, large purchases) at non-zero rates. | leakage audit (§ CON-3) |
| FR-B6 | Splice red-team batches into the world and recompute features so injected events inherit genuine history. | `test_redteam_generate_merges_into_world`, `verify --stage redteam` |

#### C. Features
| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-C1 | Compute exactly the 83 ordered `FEATURE_COLUMNS`, each with a human label. | `tests/test_schema.py` |
| FR-C2 | Enforce causality: a feature at row *t* never reads data at or after *t*. | `test_causality_under_truncation` |
| FR-C3 | Never expose a `LABEL_COLUMNS` value as a feature. | `tests/test_leakage_audit.py` (all AUC ≤ 0.99) |
| FR-C4 | Compute features in a single streaming pass per customer + one global graph pass. | performance NFR-5 |

#### D. ML core
| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-D1 | Train a histogram GBDT (300 trees, ≤63 leaves, 64 bins, early stopping) and a random forest (120 trees) with numpy alone. | `tests/test_ml.py` |
| FR-D2 | Verify the tree models numerically (against reference weights/variance on hand cases). | `tests/test_ml.py` |
| FR-D3 | Implement path-dependent TreeSHAP (O(T·L·D²)) with exact local accuracy `base + Σφ = output`. | `test_ml.py::test_treeshap_matches_brute_force_shapley` |
| FR-D4 | Report model explainability with top-k reasons and protective factors. | `detection.explain`, `/api/score`, `tests/test_detection_api.py` |

#### E. Detection & risk
| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-E1 | Split temporally (train 60% / valid 15% / test 25%) with every `attack_id` wholly in one split. | `test_detection_api.py` (split + campaign-span tests), `verify --stage blueteam` |
| FR-E2 | Offer an unseen-family split (held-out families appear only in test, with a same-threshold reference). | `test_unseen_split_excludes_holdout_from_training` |
| FR-E3 | Choose the threshold on validation at the highest recall within the FPR budget (default 1 %). | `test_metrics_risk.py` (budget tests) |
| FR-E4 | Map probability → 0-100 risk score anchored at the STEP_UP band edge; band → action (ALLOW/MONITOR/STEP_UP_AUTH/HOLD_REVIEW). | `test_metrics_risk.py` (risk-engine tests) |
| FR-E5 | Compute overall metrics, operating curve, risk-band distribution, friction summary and per-group (attack_type/difficulty) metrics. | `tests/test_metrics_risk.py`, `/api/detect` |
| FR-E6 | Record per-transaction inference latency (µs) in the metrics payload. | `evaluate()` |

#### F. Red team
| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-F1 | Generate `-n` attack scenarios at a difficulty, re-minting attack ids, and splice them into the live world. | `test_redteam_generate_merges_into_world`, `/api/redteam/generate` |
| FR-F2 | Return each scenario's anatomy: record, evasion knobs, family playbook, spliced events with per-event scores, victim timeline. | `/api/attack/{id}`, `tests/test_detection_api.py` |
| FR-F3 | Adversarial generator emits two independent batches from identical params and different RNG streams (train vs never-seen eval). | `test_adversarial_moves_actually_mutate_the_knobs`, `verify --stage redteam` |

#### G. Gap analysis & adaptive loop
| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-G1 | Score missed fraud against 10 evasion hypotheses with silhouettes of the missed segment, propensity by hypothesis, exploit knob and remediation. | `test_gap_report_is_internally_consistent`, `/api/gap` |
| FR-G2 | Retrain on adversarial train batch and report before/after on the never-seen eval batch at the same FPR budget. | `test_priority_knobs_reference_real_knob_fields`, `verify --stage loop` |
| FR-G3 | Persist gap and loop reports; expose latest loop result. | `/api/loop/latest`, store |

#### H. API & jobs
| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-H1 | Expose the full REST surface: health, config, taxonomy, runs, models, experiments, simulate, detect, score, attacks, search, attack detail, gap, loop, red-team generate, jobs, SSE. | `tests/test_detection_api.py` route coverage |
| FR-H2 | Return `202 {job_id}` immediately for simulate, red-team generate and loop; long work runs in a daemon thread. | `test_api_core_endpoints`, `test_redteam_generate_merges_into_world`, `verify --stage api` |
| FR-H3 | Provide poll (`/api/jobs/{id}`) and SSE subscribe; job records carry status, progress notes, result/error + traceback. | `test_sse_streams_generation_realtime`, `test_sse_unknown_job_emits_error_event` |
| FR-H4 | Memoise expensive pure-read endpoints (detect, gap) per (kind, run, detector key) with a TTL. | server `memo` |
| FR-H5 | Cache built worlds by config fingerprint so an identical simulate is instant. | snapshot fingerprint; `test_identical_simulate_is_reused_and_endpoints_memoise` |
| FR-H6 | Serve a synthetic run record from the live world when the DB row was cleared by a later `persist=True` simulate. | `test_cleared_run_row_is_still_readable_while_world_alive` |
| FR-H7 | Swallow client disconnects (BrokenPipe/ConnectionReset/Timeout) without emitting tracebacks. | server `_send`/`handle_error` |

#### I. Persistence & snapshot
| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-I1 | Persist runs, model runs, risk scores, attack results, gaps, loops and experiments in SQLite (POSIX-safe default path; `SG_DB_PATH` override). | `test_store_round_trips_every_table`, `test_clear_simulations_keeps_only_latest_run`, `verify --stage store` |
| FR-I2 | Snapshot a built world (pickle) + trained detector (JSON + gzipped trees) to `data/snapshot/` so `serve` boots fully populated in seconds. | snapshot CLI (`sg.py snapshot` builds `data/snapshot/`) + `serve` boot (seed_snapshot) |
| FR-I3 | Honour `SG_SEED=0` to boot an empty lab (no auto-seed). | `sg.py serve --no-seed` / `SG_SEED=0` (boots empty lab) |
| FR-I4 | Cap stored simulations so the DB stays small (clear older rows on new persist). | `Store.clear_simulations` |

#### J. CLI & frontend
| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-J1 | CLI: `build`, `train`, `redteam`, `gap`, `loop`, `demo`, `experiments`, `snapshot`, `serve`, `taxonomy`. | `verify.py --stage cli` |
| FR-J2 | Frontend: subscribe to SSE with the *named* event API and render generation/progress/done states. | `runRealtime()`; browser smoke tests |
| FR-J3 | Frontend: shared run state + cross-page caches so tab switches do not refetch expensive results. | `pages/index.jsx` |
| FR-J4 | Frontend: statically resolvable imports/exports. | `verify --stage frontend` |
| FR-J5 | Frontend: SHAP waterfall renders base value, up/down contributions and raw feature values, responsively. | UI docs; browser geometry checks |

### 3.3 Non-functional requirements

| ID | Category | Requirement | Status |
| --- | --- | --- | --- |
| NFR-1 | Correctness | Single-feature AUC for every feature ≤ 0.99 (leakage audit). | Pass |
| NFR-2 | Correctness | Feature output bit-identical when the stream is truncated at 25/50/75 %. | Pass |
| NFR-3 | Integrity | No `attack_id` spans two splits; adversarial eval batch never seen in training. | Pass |
| NFR-4 | Performance | Feature build ~60–100 k rows/s (pure Python). | Measured |
| NFR-5 | Performance | Inference at µs/txn; full `verify --quick` ~90 s; unit suite ~1 min. | Measured |
| NFR-6 | Responsiveness | Dashboard usable at 390 → 1440 px; long ops are async (never block on the 30 s dev-proxy cap). | Pass (browser-tested) |
| NFR-7 | Portability | No third-party ML import at runtime; optional backends detected but unnecessary. | Pass |
| NFR-8 | Determinism | Same config → identical world/metrics; reproducible from seed. | Pass |
| NFR-9 | Reliability | Client disconnect is normal and silent; job failures return typed error + traceback in the job record. | Pass |
| NFR-10 | Maintainability | Python core uses a shared histogram-tree primitive for both models; tests run without pytest. | Pass |
| NFR-11 | Observability | `/api/health` reports backend, ML backend, loaded worlds/detectors, default run. | Pass |

### 3.4 Data requirements

| Artefact | Format | Location | Lifecycle |
| --- | --- | --- | --- |
| World snapshot | `world.pkl` (numpy/pandas) | `data/snapshot/` | Rebuilt by `sg.py snapshot` |
| Detector | `detector.json` + `model.json.gz` | `data/snapshot/detector/` | Regenerated on train |
| Attack knowledge base | JSON (7 families) | `data/attack_taxonomy.json` | Static data asset |
| Run/store | SQLite | `~/.local/state/sovereignguard/` (env-overridable) | Grows on persist; simulations capped |
| Experiment artefacts | JSON (raw numbers + env) | `experiments/results/` | Written by `sg.py experiments` |
| Generated datasets | CSV/parquet per module | `data/synthetic/`, `data/attacks/`, `data/evaluation/` | Temp/derived |

Behavioural rate requirements (must not be zero): new-merchant rate, device-change
rate, travel propensity, new-beneficiary rate and large-purchase share are all
non-zero so no flag becomes a perfect fraud oracle.

---

## 4. Verification acceptance

| Gate | Command | Passing criterion | Current |
| --- | --- | --- | --- |
| Unit suite | `python tests/run_tests.py` | All tests pass, 0 failures | ✓ 92/92, ~56 s |
| End-to-end | `python verify.py --quick` | All 14 stages assert-pass | ✓ 14/14 |
| Frontend build | `cd frontend && npm run build` | Clean production build | ✓ |
| API contract | `verify.py --stage api` + browser smoke | No console/page errors | ✓ |
| Leakage/causality/campaign | dedicated tests inside suite | All green | ✓ |

---

## 5. Version history

| Version | Date | Change |
| --- | --- | --- |
| 1.0 | 2026-08-30 | Initial SRS reflecting implemented status; added async-job/SSE contract (FR-H2–H3), snapshot reboot (FR-I2–I3), cleared-run fallback (FR-H6), responsive waterfall (FR-J5). |