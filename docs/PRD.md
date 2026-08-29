# SovereignGuard — Product Requirements Document (PRD)

|     | |
| --- | --- |
| **Product** | SovereignGuard — AI Red Team / Blue Team Payment-Fraud Testing Lab |
| **Version** | 1.0 (current implementation status) |
| **Date** | 2026-08-30 |
| **Status** | Shipped (MVP feature-complete; all verification gates green) |
| **MasterCard Hackathon 2026** | Track: AI-powered fraud / security |

---

## 1. Executive summary

SovereignGuard is a synthetic payment-fraud laboratory. It generates a believable
population of ~2,000 Indian customers and merchants, streams ~360,000 realistic
transactions over a 45-day window, injects hundreds of fraud campaigns drawn from
a seven-family attack taxonomy, then pits a from-scratch machine-learning detector
(histogram GBDT + random forest + TreeSHAP, **zero third-party ML libraries —
numpy only**) against red-team adversaries. Every step — identify, generate,
attack, detect, explain, adapt, retest — runs end-to-end and is verifiable.

The system exists to answer one question the industry needs evidence on:
*which fraud is actually hard for a well-tuned deployment, and why?* It does this
without any real customer data.

All verification gates are currently green: **92 unit tests pass**, all
**14 end-to-end verification stages** pass, the Next.js dashboard builds cleanly,
and the browser-tested UI runs with no console errors.

---

## 2. Problem statement

Fraud teams live on a treadmill: models learn last month's fraud, and attackers
drift. The blocker is never idea generation — it is *test data*. Production data
is private, sparse on fraud, and labelled after the fact; public datasets are
stale and fixed; and building a believable synthetic payment world by hand is
months of work.

**Opportunity:** a reproducible synthetic lab — with an honest detector, a
deliberate adversary, and per-transaction explanation — that quantifies the
residual gap between any model and what a motivated attacker can still get away
with, then measures whether retraining on adaptive attacks actually closes it.

---

## 3. Non-goals (explicitly out of scope for v1)

- **No real payment data and no production inference.** SovereignGuard is a
  testing laboratory, not a runtime fraud engine.
- **No third-party ML dependency.** No XGBoost / LightGBM / scikit-learn in the
  runtime path; the models are implemented in numpy and verified against the
  mathematical definitions (not against a library).
- **No claim that thresholds are production policy.** Risk bands and operating
  points are prototype policy values, documented as such.
- **No UI testing framework.** The frontend is verified by a clean production
  build, static import/export resolution, and browser smoke tests — status is
  "verified", not "unit-tested".
- **No production-grade persistence.** SQLite + pickle snapshots are lab
  artefacts designed for fast reboot, not a bank's storage layer.

---

## 4. Target users

| Persona | Use | Primary surfaces |
| --- | --- | --- |
| **Fraud data scientist** | Calibrate a model against believable synthetic fraud; understand WHY a decision was made | Blue Team Detection, Explainability |
| **Red-team builder** | Author and launch evasion campaigns; inspect how they bypass the defence | Red Team Simulator, Attack Studio, Attack Intelligence |
| **Security officer / challenge judge** | Watch the ADAPT loop close the gap; read the 7-family taxonomy and gap hypotheses | Overview, Gap Analysis, Adaptive Loop |
| **Planner / architect** | Deploy the lab in a sandbox or Docker; regenerate data at any scale | CLI, REST API, Docker |

---

## 5. Product vision

> **Identify** the attack. **Generate** a world it would live in. **Attack** an
> honest detector. **Detect** and measure the miss. **Explain** every decision.
> **Adapt** the blueprint. **Retest** — and prove the improvement is
> generalisation, not memorisation.

Vision statement: *Every fraud-control question your data cannot answer, this lab
can — from a deterministic seed.*

---

## 6. Success metrics (how "done" is measured)

| Metric | Target | Current status |
| --- | --- | --- |
| Unit tests passing | All green, no pytest required | **92 / 92** (~56 s) |
| End-to-end verification stages | All green | **14 / 14** (`verify.py`) |
| Frontend production build | Clean | **Clean** (`npm run build`) |
| Label leakage (single-feature AUC) | No feature > 0.99 | **Audited, 3 historical leaks fixed** |
| Feature causality | Bit-identical under truncation at 25/50/75% | **Structural + tested** |
| Campaign leakage across splits | No `attack_id` in two splits | **Enforced + verified** |
| FPR operating budget | ≤ 1 % on validation | `TARGET_FPR_BUDGET = 0.010` |
| Detection inference latency | µs-scale per transaction | Recorded on every evaluate |

---

## 7. Product pillars and their features

The hero loop is `IDENTIFY → GENERATE → ATTACK → DETECT → EXPLAIN → ADAPT → RETEST`.

### 7.1 IDENTIFY — attack knowledge base
- A 7-family attack taxonomy in `data/attack_taxonomy.json`: account takeover,
  transaction manipulation, synthetic identity, merchant fraud, phishing (payment
  link), social engineering, multi-stage. Each entry carries severity,
  base-rate prior, kill-chain stages and evasion playbook.
- REST endpoints expose the taxonomy per family.

### 7.2 GENERATE — synthetic payment world
- **7 behavioural personas** (student, young professional, family, senior, gig
  worker, small business, high-net-worth) drive all legitimate behaviour with
  lognormal amounts, method/category affinities, night activity, travel,
  device-change and new-merchant propensities.
- **14 merchant categories**, 20 cities (plus 2 attacker-friendly offshore hubs),
  4 payment methods, 4 channels, 4 transaction types.
- **Honest customers do suspicious things** — non-zero life-event rates (new
  devices, beneficiaries, travel, large purchases) keep every signal a
  non-oracle.
- **5 scale profiles** (`nano` → `full`; 300 → 100,000 customers) share one seed
  + config fingerprint, so every build is deterministic and reproducible.

### 7.3 ATTACK — red team
- Attack campaigns are time-resolved multi-stage scripts (not bolted-on rows):
  preprocessing (credential access, device prep, mule accounts), execution
  (drain, purchase, transfer), each event spliced into the world and assigned a
  legitimately-derived technique.
- **4 difficulty levels** (EASY / MEDIUM / HARD / ADVERSARIAL) gate which
  evasion knobs a campaign may touch.
- `redteam generate -n N` and the API (`/api/redteam/generate`, async job)
  mint new campaigns; Red Team Simulator runs the full loop.

### 7.4 DETECT — blue team
- **83 causal features** across 17 groups (amount, velocity, device, location,
  merchant, temporal, account/identity, session/auth, method/channel one-hots,
  sequence/graph).
- Detector implemented from scratch: **histogram GBDT** (300 trees, max 64 bins,
  early stopping) and **random forest** (120 trees), both built on one shared
  histogram tree primitive.
- **Temporal + campaign-grouped splits.** Train/validate/test are time-ordered;
  every event of an `attack_id` stays in one split. A second split mode holds out
  whole families to test zero-day transfer.
- Operating point chosen on **validation only**, at a false-positive budget
  (`≤ 1%`), never on test.

### 7.5 EXPLAIN — TreeSHAP
- **Path-dependent TreeSHAP** implemented from the paper; O(T·L·D²), verified
  against a brute-force evaluation of the Shapley definition on small trees.
- Per-transaction: reasons (risk-increasing) and protective factors (risk
  decreasing), base value, risk band, action, and a human-readable narrative.
- Explainability dashboard: risk gauge, animated transaction location, and the
  responsive SHAP waterfall (red = pushes toward fraud, teal = pushes away).

### 7.6 ADAPT — gap analysis + adaptive loop
- **10 evasion hypotheses** (low value, slow pacing, familiar device, familiar
  geography, existing beneficiary, merchant mimicry, no credential trace, low
  velocity footprint, aged synthetic identity, sequence-only). Each identifies
  the evasion knob and a proposed signal remediation.
- **Adversarial loop, anti-cheat by construction:** two independent adversarial
  batches from identical parameters but different RNG streams — one retrains the
  model, the other is *never seen during training* and is used for every reported
  number. Reported recall gains are therefore genuine generalisation, not
  memorisation.
- Blueprint retrain (`/api/loop`, async) returns a hardened detector and a
  before/after comparison at the same FPR budget.

### 7.7 RETEST — experiments & verification
- Six measured experiments: baseline trade-off, attack diversity, unseen-family
  transfer, adversarial materiality, adaptive-loop gain, false-positive honesty.
  JSON artefacts land in `experiments/results/`.
- `verify.py` re-runs the whole pipeline in 14 assertive stages; `--quick`
  (~90 s) and `--full` (~15 min) profiles cover the same properties at different
  scales.

---

## 8. Key user stories

| ID | As a… | I want to… | So that… | Status |
| --- | --- | --- | --- | --- |
| US-01 | analyst | click "New simulation" and watch the world build with a live progress feed | I never wonder whether the pipeline is working | Done |
| US-02 | analyst | see detection metrics, risk-band distribution and per-family recall | I can judge where the defence is structurally weak | Done |
| US-03 | analyst | score one transaction and see exactly why it was flagged | I can defend the decision to a reviewer | Done |
| US-04 | red-teamer | generate N new attack scenarios at a difficulty and inspect each one | I can test ideas without hand-writing campaigns | Done |
| US-05 | red-teamer | open a scenario and replay its events, scores and evasion knobs | I understand the mechanism that evaded us | Done |
| US-06 | judge | run the gap analysis and see each of the 10 hypotheses scored with remediation | I can evaluate research depth at a glance | Done |
| US-07 | judge | run one adaptive-loop command and see before/after recall on never-seen attacks | I trust the improvement is real | Done |
| US-08 | architect | `open docs/SDD.md … python sg.py snapshot && python sg.py serve` | I can replicate the whole lab in minutes | Done |
| US-09 | analyst | use the dashboard on a phone/tablet | the console is responsive, not desktop-only | Done |

---

## 9. Release / current status

### 9.1 Shipped
- Full pipeline + REST + dashboard; everything below is reachable from the UI.
- **9 dashboard views:** Overview, Live Monitor, Attack Intelligence, Red Team
  Simulator, Attack Studio, Blue Team Detection, Explainability, Gap Analysis,
  Adaptive Loop.
- Async job model (`202 {job_id}` + poll/SSE) for simulate, red-team generate and
  adaptive loop — nothing slow blocks the 30 s dev-proxy window.
- Snapshot reboot: `serve` restores a trained world + detector in ~seconds.
- Responsive dark-theme console (verified at desktop, tablet and mobile widths).

### 9.2 Verification evidence (2026-08-30)
- `python tests/run_tests.py` → **92 passed, 0 failed** (~56 s).
- `python verify.py --quick` → **14/14 stages pass**.
- `cd frontend && npm run build` → clean; dashboard smoke-tested headlessly with
  zero console errors.
- Demo world reference: ~2,061 customers · 1,327 merchants · ~361,162
  transactions · 3,843 fraud events · 449 scenarios · 7 attack families · 83
  features · 45-day window.

### 9.3 Known limits / future work
- Confidence intervals are wide at `nano`/`tiny` scale by design; load-bearing
  results should come from `demo`.
- Dashboard interactions are smoke-tested, not unit-tested; a UI test harness is
  the natural next investment.
- Graph/sequence model (per the `SEQUENCE_ONLY` remediation) and
  production-style persistence remain future work.
- `data/snapshot/world.pkl` (~283 MB, binary) is rebuilt on demand; it is
  excluded from source hygiene concerns.