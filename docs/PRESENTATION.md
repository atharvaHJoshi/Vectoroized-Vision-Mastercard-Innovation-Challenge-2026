# SovereignGuard
## An AI Red Team–Blue Team Payment Security Laboratory

**Adversarial AI for Payment Security — Hackathon Solution Walkthrough**

> This document is a complete solution presentation, from ideation to a working
> prototype. Each section maps to one slide (or a slide cluster) so it can be
> presented directly or converted to a `.pptx` deck with pandoc/marp.

---

## Table of contents

1. [Problem Statement](#1-problem-statement)
2. [Solution Proposed](#2-solution-proposed)
3. [Solution Features & Comparison with Existing](#3-solution-features--comparison-with-existing)
4. [Unique Technology Stack](#4-unique-technology-stack)
5. [How We Segregated Attack Families](#5-how-we-segregated-attack-families)
6. [How We Generate Synthetic Data](#6-how-we-generate-synthetic-data)
7. [Technology Deep-Dive](#7-technology-deep-dive)
8. [Developed Prototype — System Architecture](#8-developed-prototype--system-architecture)
9. [Scalable System Architecture & Design Concepts](#9-scalable-system-architecture--design-concepts)
10. [Data Flow Diagram (Current)](#10-data-flow-diagram-current)
11. [ML Architecture — Data Collection to Training](#11-ml-architecture--data-collection-to-training)
12. [Future Scope](#12-future-scope)
13. [Challenges We Faced](#13-challenges-we-faced)
- [Appendix A — Headline Metrics](#appendix-a--headline-metrics)
- [Appendix B — Demo Script](#appendix-b--demo-script)

---

# 1. Problem Statement

## Fraud defence is fundamentally *reactive*

Conventional payment fraud detection is built on a simple, now-broken assumption:
**attackers are slow and repeatable, so defenders can learn from the last attack.**

- **Rules** are written *after* a pattern is observed.
- **Models** are trained on *historical* fraud.
- **Defences** are updated *once attackers have already found the weakness.*

## Generative AI breaks that model completely

The defining effect of GenAI on fraud is not new payment rails — it is a collapse
in the cost of producing a **new variant** of an attack.

| Legacy world | GenAI world |
|---|---|
| A few high-volume attack templates | Very many **low-volume variants** — each seen once |
| Scripts replayed by humans | Autonomous, personalised, translated, voice-cloned attacks |
| Slow iteration (weeks per campaign) | Minute-scale iteration against the defence |
| Attacks learned *from* you (reuse of stolen patterns) | Attacks **built to evade you** (probes + adaptation) |

## The market reality in numbers

> Figures below are public-industry measurements, cited for context, not from
> our synthetic lab.

- **Voice-clone / deepfake attacks on the rise:** deepfake-related fraud attempts
  surged sharply in 2025–26 — e.g. a **+94%** year-on-year rise in deepfake
  detection across UK banking attempts and a claimed **+180%** jump in
  "advanced-deception" fraud categories.
- **KYC liveness bypass is industrialised:** injection attacks (feeding a
  synthetic face into a camera model instead of a real lens) on one platform
  rose **+1,151%** in H2 2025; deepfakes reached roughly **7% of fraud attempts**
  screened by an identity-verification vendor in 2024, a **4×** jump year on year.
- **Agentic fraud is live:** 2026 industry forecasts describe "fraud-with-agency"
  — attacks that observe a defence, learn its boundary, and act autonomously inside
  live financial ecosystems (polymorphic phishing, deepfake-as-a-service,
  synthetic identity farms, invoice-timed vendor impersonation, ghost-touch
  biometric session hijacking).
- **Authorized Push Payment (APP) / authorised fraud** is the fastest-growing
  dollar category — nothing is compromised; the victim moves their own money
  while every authentication control shows *green*.

## The core problem for any payment security team

1. **You cannot train on what has not happened yet.** Real fraud data arrives
   *after* the loss.
2. **A static benchmark overstates durability.** A model that scores well on its
   training distribution collapses when an attacker *aims at its weakness*.
3. **Evaluating on the same attacks you trained on proves nothing.** (Trivially
   ~99% recall — worthless.)
4. **Integration is dangerous and slow.** Realistic attack experiments on a live
   payment portfolio are expensive, risky and often impossible.

---

# 2. Solution Proposed

## SovereignGuard — a continuous adversarial stress-testing lab

Instead of waiting for real fraud, SovereignGuard builds a **controlled synthetic
payment environment** in which the defence is attacked *before* a real customer is.

```
    IDENTIFY → GENERATE → ATTACK → DETECT → EXPLAIN → ADAPT → RETEST
```

It is **not another fraud classifier.** It is a continuous stress-testing and
improvement layer that:

1. **Identifies** the attack surface (a parameterised GenAI attack knowledge base).
2. **Generates** high-fidelity synthetic customers, merchants and transactions —
   *fully synthetic, no real data needed*.
3. **Attacks** its own defence with four evasion skill levels, including
   **ADVERSARIAL** — generated against the detector's *measured* weaknesses.
4. **Detects** with a from-scratch GBDT / Random Forest on 83 strictly-causal
   behavioural features.
5. **Explains** every decision with a TreeSHAP implementation verified against the
   Shapley definition.
6. **Shows the gap** — ten named evasion hypotheses, ranked by lift.
7. **Adapts and retests** — generates attacks aimed at the gap, retrains, and
   proves improvement on attacks the retrained model *never saw*, at an
   **identical false-positive rate**.

## Headline result (measured, honest)

The system diagnosed its own weakness, generated adversarial attacks targeting it,
retrained, and improved — **on an adversarial batch the retrained model never saw**,
at an identical false-positive rate:

| | Recall | F1 | Attacks missed | FPR |
|---|---|---|---|---|
| Baseline defence | 22.0% | 0.357 | 2,863 | 0.991% |
| Hardened defence | **35.5%** | **0.519** | **2,367** | 0.991% |
| **Change** | **+13.5 pts** | **+16.2 pts** | −496 | *matched* |

**And the cost, which is the most important number:** recall on the *original*
attack distribution fell **11.1 points** (51.4% → 40.3%). That trade-off is a real
finding, not a failure — it is exactly what a stress-testing layer exists to
surface *before* a model reaches production.

## Why this solves the problem

| Problem | Solution |
|---|---|
| Cannot train on future fraud | Synthetic enemies generated *today* from a GenAI attack model |
| Static benchmarks overstate durability | Adversarial attacks aimed at measured weakness (recall 59%→26% when aimed at) |
| "Training on test" inflates results | Two independent adversarial batches + matched FPR + regression check |
| Real-data experiments are risky | Everything is a synthetic simulation — zero compliance risk |
| Ops teams cannot explain red flags | TreeSHAP reason codes + risk bands + gap analysis attribution |

---

# 3. Solution Features & Comparison with Existing

## What the market/SOTA does today

| Capability | Traditional rules engine | Static ML fraud model | Generic synthetic data (vendor) |
|---|---|---|---|
| Attack source | Written scripts, post-incident | Historical real fraud | Fixed templates, weak realism |
| GenAI attack modelling | None | None | Rarely; labelled "GenAI" without behaviour |
| Evasion awareness | None | Threshold at one FPR | None |
| Adaptation | Manual rule updates | Periodic retrain | None |
| Explainability | Rule fired (opaque) | Feature importances (opaque), SHAP library | None |
| Honest evaluation | FPR often ignored | Train/test on same distribution, leak risk high | Not applicable |
| Self-improvement loop | No | No | No |

## What SovereignGuard adds

### The five pillars

1. **Identify — Fraud Intelligence Engine.** A parameterised knowledge base of
   attack families (7 today, extending to **13 GenAI-native families**). Each
   entry specifies target, payment rails, the role of GenAI, behavioural changes
   in the event stream, expected defender signals, stage sequence and mitigations.

2. **Generate — Synthetic Data Engine.** Fully synthetic population: 7 behavioural
   personas, 14 merchant categories, 20 cities, realistic habit modelling, and
   the crucial rule that **legitimate customers do suspicious things** (non-zero
   `LEGIT_EVENT_RATES`) so that no feature becomes a perfect fraud oracle.

3. **Attack — Red Team.** Seven attack sequence generators, spliced into a real
   victim timeline so **every feature is earned from history, not stamped on**.
   Four evasion skill levels (EASY / MEDIUM / HARD / ADVERSARIAL).

4. **Detect — Blue Team.** Two models built from scratch in numpy (histogram GBDT
   and Random Forest) on **83 causal features**, with risk bands and reason codes.

5. **Adapt & Retest.** Gap analysis (10 hypotheses) → adversarial generator →
   retrain → retest on a **held-out** adversarial batch at a **matched FPR**,
   with a regression check.

### Headline capability comparison

| Dimension | Traditional | Static model | Ours |
|---|---|---|---|
| Attack families modelled | 0–3 scripts | 1 "fraud" class | 7 (→13) parameterised families |
| Evasion levels | none | none | 4 incl. ADVERSARIAL (self-attack) |
| Features | 5–20 rules | vendor feature pack | **83 strictly-causal features**, 10 dimensions |
| Improves itself | no | no | **yes** — adaptive loop with dual-batch anti-cheat |
| Honest about regressions | no | no | **yes** — baseline regression reported alongside gain |
| Leakage audit | manual | AUC sanity | **automated** — single-feature AUC ≤ 0.99 gate |
| Causality proof | n/a | assumed | **proven** — bit-identical output under stream truncation |
| Explainability quality | rule text | importances | TreeSHAP verified to ~2.7e-08 vs brute-force Shapley |
| Reproducibility | n/a | hyperparam dump | single seed `20260823` + a `RunConfig` fingerprint |
| Boot-to-dashboard | n/a | n/a | ~seconds from a snapshot |

## Feature catalogue (83 features, 10 dimensions)

- **Amount (9):** amount, log amount, ratios vs customer median / 7d max / 30d
  p95, merchant median, z-score, round-number flag, % of credit limit.
- **Velocity (13):** txn counts in 10 min / 1 h / 24 h / 7 d, value sums, ratio to
  median day, seconds since previous txn, distinct merchants/devices/cities,
  declines, escalating-amount run.
- **Device (7):** new-device flag, device age, txn count, customer share, emulator,
  rooted, reputation.
- **Location (6):** new-city flag, distance from home, distance from previous txn,
  implied speed, high-risk location, city count.
- **Merchant (8):** new-merchant flag, intrinsic risk, age, chargeback rate, CNP
  share, volume (log), customer–merchant pair count, category affinity.
- **Temporal (6):** hour, weekday, night/weekend flags, hour deviation, unusual-hour.
- **Account / identity (6):** account age, KYC level, identity-doc score,
  contactability, digital footprint, lifetime txn count.
- **Session / auth (12):** password/profile changed, failed logins, session
  duration, typing-cadence deviation, ASN hosting/VPN, new beneficiary,
  beneficiary age, SIM swap, inbound call active, payment-link referred.
- **Method / channel one-hots (12) and Sequence / graph (4):** stage index,
  customer risk events in 24 h, beneficiary in-degree, merchant new-customer share.

---

# 4. Unique Technology Stack

## A deliberate, defensible deviation

The original build plan specified XGBoost / LightGBM, SHAP and FastAPI. The build
environment had **no network access**, so none could be installed. Rather than
stub them out, the ML core is implemented **from scratch**.

| Planned | Built | Why it is defensible |
|---|---|---|
| XGBoost / LightGBM | **Histogram GBDT in numpy** | Verified to **98.6% of Bayes-optimal AUC** on a synthetic XOR problem (0.8842 vs theoretical 0.8969) |
| scikit-learn Random Forest | **Bagged trees, Gini-equivalent** | Squared-error splitting on a 0/1 target is provably equivalent to Gini — one tree builder serves both models |
| `shap` | **Path-dependent TreeSHAP** | Verified exact against brute-force enumeration of the Shapley definition (2.7e-08 absolute agreement) |
| FastAPI | **`http.server` REST API** | Zero dependencies; identical JSON contracts; same routes a FastAPI app would expose |
| PostgreSQL | **SQLite (+ `postgres_ddl()`)** | Same SQL; swap the connection, not the queries |

## The stack at a glance

```
┌────────────────────────────────────────────────────────────────┐
│  RUNTIME (core):  Python 3.9+  ·  numpy  ·  pandas   (only!)   │
│  ML:     histogram GBDT  ·  Random Forest  ·  TreeSHAP         │
│          all hand-written in numpy — no sklearn/XGBoost/SHAP   │
│  DATA:   SQLite (PostgreSQL DDL included)  ·  pickle snapshots │
│  API:    stdlib http.server REST  ·  JSON  ·  SSE streams      │
│  FRONTEND: Next.js 14  ·  React  ·  plain JS/JSX (no TS)       │
│  DEVOPS: docker compose  ·  shell CLI (sg.py)                  │
└────────────────────────────────────────────────────────────────┘
```

## Why this is a feature, not a limitation

- **Zero-install core**: `python sg.py demo` runs the whole story with only
  `numpy` and `pandas`. No environment pain, no version hell — ideal for a
  hackathon-judging environment.
- **No accuracy anywhere**: at 1% prevalence a model that approves everything
  scores 99% accuracy and is worthless. SovereignGuard reports recall at a
  fixed FPR, ROC-AUC, PR-AUC and bootstrap CIs only.
- **Correctness proofs replace library trust**: the tree model is verified against
  a known Bayes-optimal answer; TreeSHAP is verified against the definition itself;
  `detection.optional_backends()` cross-checks against real XGBoost/LightGBM/SHAP
  when those happen to be installed.

## Effort/Dependency economics

| Dimension | Value |
|---|---|
| Runtime deps | 2 (`numpy`, `pandas`) |
| Test runner | `tests/run_tests.py` — no pytest required (pytest works if present) |
| Unit tests | **92**, including 3 load-bearing proof tests |
| End-to-end verify | `verify.py` — **14 asserting stages**, not just "it ran" |
| Boot to populated dashboard | ~seconds (snapshot reload) vs ~2 min cold build+train |

---

# 5. How We Segregated Attack Families

## Segregation principle

Attacks are segregated along **four orthogonal dimensions**, all driven from a
single knowledge base (`data/attack_taxonomy.json`) + generator registry:

1. **Family** — *what* is attacked (7 families today → 13 with GenAI-native
   additions).
2. **Difficulty** — *how well* the attacker hides (4 skill levels).
3. **Victim context** — *who* is targeted: the victim persona, geography, cash-out
   merchant pool (sampled, so diversity is measured, not asserted).
4. **Stage sequence** — *how* the attack unfolds over time (each family has a
   distinct ordered stage list).

The taxonomy is **parameterised, not enumerated**: the Red Team *samples* the
parameter space instead of replaying fixed scripts — the only correct response to
a GenAI attacker.

## The seven current families

| Family | Severity | Target | Why it is hard |
|---|---|---|---|
| **ACCOUNT_TAKEOVER** | CRITICAL | Account + outbound payment | Hard variant hijacks an existing *session* — no new device at all |
| **TRANSACTION_MANIPULATION** | HIGH | The fraud engine's thresholds | Every single transaction is unremarkable *by construction* |
| **SYNTHETIC_IDENTITY** | HIGH | Account origination / credit | Behaves *better* than a real customer until the bust-out |
| **MERCHANT_FRAUD** | HIGH | Acquiring / settlement | A fake storefront looks like a new legitimate one |
| **PHISHING_PAYMENT_LINK** | HIGH | Customer intent (authorised) | The customer genuinely authorises; every auth passes |
| **SOCIAL_ENGINEERING** | CRITICAL | Customer decision-making | Nothing is compromised — own device, own location |
| **MULTI_STAGE** | CRITICAL | Seams between controls | Only the *ordering* of events is incriminating |

## Where GenAI fits — the amplification note

> "Generative AI does not invent new payment rails; it collapses the cost of
> personalisation, translation, voice cloning and iteration. The practical
> consequence is a shift from a few high-volume templates to very many
> low-volume variants. That is why this taxonomy is parameterised rather than
> enumerated."

Every existing family carries a `genai_role` so the knowledge base already
describes *how AI amplifies it* — e.g. credential lists triaged by a model +
per-victim phishing pages + voice clones (ACCOUNT_TAKEOVER); real-time voice
cloning and adaptive conversational agents (SOCIAL_ENGINEERING); coherent
fabricated identity packages with generated document/selfie media for KYC
(SYNTHETIC_IDENTITY).

## Planned GenAI-native families (differentiation)

New distinct entries so "diversity of attacks identified" is explicit:

| New family | GenAI mechanism |
|---|---|
| **DEEPFAKE_ATO** | Voice-clone call-centre reset → session hijack |
| **CONVERSATIONAL_AGENT** | Agentic vishing; sustains the call, adapts to objections, coaches past warnings |
| **AGENTIC_APP** | Prompt-injection of the customer's own AI assistant → authorised push abuse |
| **DEEPFAKE_KYC** | Synthetic-media identity + liveness-injection (extends SYNTHETIC_IDENTITY path) |
| **MULE_NETWORK** | LLM-orchestrated mule-account farms; fan-out→converge beneficiary graph |
| **INVOICE_TIMED_BEC** | Vendor impersonation timed to the buyer's billing cadence |

Each entry is a full simulation specification (target, surfaces, behaviour change,
signals, stages, difficulty variants, mitigations, evidence) — no operational
fraud guidance.

## Segregation orchestration contract

```
attack_taxonomy.json  ──►  taxonomy.validate()  ──►  C.ATTACK_TYPES
        │                                            │   (single source of truth)
        ▼                                            ▼
GENERATOR MAP (families.py)                    RedTeam.generate(attack_types,
  ACCOUNT_TAKEOVER      → gen_account_takeover      difficulty_mix, n)
  ...7 (→13) entries   → gen_*                     │
                                                    ▼
                                       samples family by prior (sums to 1),
                                       picks victim persona, city, cashout,
                                       difficulty split, splice into timeline
```

**Guarantees pinned by tests:** taxonomy matches `C.ATTACK_TYPES` exactly; every
entry is complete; each family's `expected_signals` reference *real* features; the
type mix sums to 1; every generator produces valid sequences; all events of one
`attack_id` stay in one train/test split (**campaign leakage forbidden**).

---

# 6. How We Generate Synthetic Data

## Three-layer synthetic engine

### Layer 1 — Population (`generators/population.py`)

| Entity | Detail |
|---|---|
| **Customers** | 7 behavioural personas by weight: STUDENT (0.16), YOUNG_PROFESSIONAL (0.22), FAMILY (0.21), SENIOR (0.12), GIG_WORKER (0.11), SMALL_BUSINESS (0.10), HIGH_NET_WORTH (0.08) |
| Persona habit model | lognormal amount `(amount_mu, amount_sigma)` in INR, `txns_per_day`, `night_activity`, `travel_propensity`, `new_merchant_rate`, `device_change_rate`, `transfer_share`, per-persona payment-method weights and category affinities |
| **Merchants** | 14 categories (FOOD, GROCERY, ECOMMERCE, MOBILITY, UTILITIES, FUEL, ENTERTAINMENT, P2P_TRANSFER, TRAVEL, HEALTHCARE, EDUCATION, GAMING, FINANCIAL_SERVICES, CRYPTO_GATEWAY) each with ticket distribution, intrinsic risk, CNP share, peak hours |
| **Cities** | 20 with geo-coordinates and population weights (18 Indian metros + Dubai + Singapore); high-risk: Dubai, Singapore, Guwahati, Lucknow |
| **Devices** | Realistic registry: emulator/root flags, reputation, first-seen age |

### Layer 2 — Legitimate traffic (`generators/transactions.py`)

- **Hour-curve simulation**: each customer `txns_per_day` events per day, hours
  drawn from category peak hours + persona night activity; ~98.4% approved.
- **The 62/38 amount blend**: each amount mixes the customer's own price point with
  the category's ticket size in log space — the same customer spends differently at
  a cinema and a travel agent; two customers spend differently at the same grocer.
  Without this, `amount_ratio_customer_median` would be noise.
- **Compressed realism**: trips (travel), password/profile changes, failed-login
  bursts, new payees, device top-ups — from `LEGIT_EVENT_RATES`.

### Layer 3 — The honesty rule (the most important decision in the project)

```
LEGIT_EVENT_RATES = {
    password_change_per_year:     0.85,
    profile_change_per_year:      1.6,
    new_beneficiary_per_year:     5.2,
    failed_login_burst_per_year:  3.1,
    large_purchase_share:         0.021,   # txns at 5–18x the customer median
    device_reinstall_per_year:    1.4,
}
```

**Real people change phones, travel, add payees, mistype passwords, and buy
something 12× their normal amount.** If any of these rates were **zero**, the
corresponding flag (e.g. `is_new_device`) would become a *perfect fraud oracle* —
recall hits 100% and every reported number is meaningless. This rule is pinned by
three tests (non-zero & <10%).

### Sanity checks on a representative run (400 customers · 30 days · 47,476 txns in 2.4 s)

| Property | Value | Sanity check |
|---|---|---|
| Median amount | ₹857 | plausible retail ticket |
| 99th percentile | ₹29,307 | long tail, not absurd |
| Transfers | 12.7% | reasonable A2A share |
| Overnight (00–06) | 12.1% | matches the hour curve |
| **New beneficiary** | **0.09%** | **rare but non-zero — the leakage guard** |

## Attack injection — "earned, not stamped"

Attack generators return **event sequences** (using exactly the same columns as
legitimate traffic). Sequences are spliced into the victim's existing timeline and
**features are recomputed over the whole merged stream**. An attack row's velocity,
device-novelty and beneficiary-age features are therefore genuinely *earned from
history* — a HARD attack is actually hard.

### Difficulty gradient (measured; target = LEGIT, converge toward it)

| Feature | LEGIT | EASY | MEDIUM | HARD |
|---|---|---|---|---|
| Amount vs customer median | 2.0× | 15.7× | 7.2× | **2.8×** |
| New-device rate | 0.019 | 0.075 | 0.063 | **0.023** |
| Distance from home (km) | 27 | 835 | 226 | **92** |
| Amount % of credit limit | 5.7% | 42.8% | 20.3% | **8.1%** |

### Diversity is measured, not asserted

`AttackBatch.diversity_report()`:
- family entropy **0.987**, victim-persona **0.999**, geography **0.963**
- **4.4 orders of magnitude** range in amount
- **27 distinct attack stages** across families

### Determinism & scale profiles

- Single seed `SEED = 20260823` (overridable), fixed epoch `SIM_EPOCH` (2025-01-01),
  so every run is comparable.
- Scale profiles for iteration speed vs. load-bearing results:

| Profile | Customers | Merchants | Days | Attacks/family | ~Transactions |
|---|---|---|---|---|---|
| nano | 300 | 200 | 21 | 80 | ~16k |
| tiny | 400 | 300 | 30 | 120 | ~31k |
| demo (default) | 2,000 | 1,200 | 45 | 400 | ~234k |
| large | 10,000 | 4,000 | 60 | 1,200 | ~1.6M |
| full | 100,000 | 20,000 | 90 | 4,000 | ~23M |

---

# 7. Technology Deep-Dive

## From-scratch ML core (`sovereignguard/ml/`)

### Histogram GBDT (`tree.py`, `models.py`) — the flagship model

- **Histogram approximation**: features binned into fixed histograms; split search
  operates on the histogram, enabling the histogram-subtraction trick.
- **Logistic loss with second-order gain** — the Newton step uses both gradients
  and Hessians for a path-dependent update.
- **Row & column subsampling** per iteration for regularisation and speed.
- **Early stopping** on a validation metric; `best_iteration` retained.
- Same tree builder powers the **Random Forest** (bagging; squared-error splitting
  on a 0/1 target is provably equivalent to Gini).

**Correctness evidence:** on a synthetic XOR-interaction problem with a known
Bayes-optimal AUC 0.8969, the GBDT reached **0.8842 = 98.6% of the theoretical
maximum**, and recovered exactly the four true signal features.

### TreeSHAP (`treeshap.py`)

- Path-dependent tree attribution computed over the ensemble.
- **Verified against brute-force enumeration** of the Shapley definition over all
  2^M subsets: **agreement to 2.7e-08 absolute** on values of magnitude ~0.36,
  flat across tree depths 2–6 (an indexing bug would compound with depth).
- **Local accuracy is asserted at runtime**: `base + Σφ == model output`.
- Output drives the explainability UI (risk reason codes + waterfall chart).

## Feature engineering under a causality contract

- 83 features computed in one **streaming pass** over the sorted transaction
  stream in `features.py`.
- **Structural causality**: history is appended *after* a row's features are
  emitted, so features for row *t* use only data strictly before *t*.
- **Proof**: `test_causality_under_truncation` rebuilds features on the stream
  truncated at 25% / 50% / 75% and asserts the first *k* rows are **bit-identical**.
  Any forward-peek (unshifted groupby, full-series mean, wrong rolling closure)
  would change the past when the future is removed.

## Evaluation discipline (`evaluation/metrics.py`, `risk.py`)

- Ranking metrics only: ROC-AUC, PR-AUC (stepwise, no interpolation), recall at a
  **matched false-positive budget** (default 1%, `SG_TARGET_FPR`).
- **Threshold policy**: highest-recall threshold whose FPR on *legitimate* traffic
  ≤ budget (chosen on validation).
- **Bootstrap confidence intervals** (percentile) so deltas are judged against noise.
- **Risk bands → action policy** (prototype thresholds, tunable):

| Band | Score | Action |
|---|---|---|
| LOW | 0–30 | ALLOW — no friction |
| MEDIUM | 30–60 | MONITOR — approve, log for review |
| HIGH | 60–80 | STEP_UP_AUTH — challenge before settlement |
| CRITICAL | 80–100 | HOLD_REVIEW — fraud-analyst queue |

## Splitting discipline

- **Temporal**: train on the earliest window; all events of one `attack_id` land in
  the same split (campaign-grouped). Random shuffling would let the model see a
  customer's future and would split a 10-event takeover across train/test.
- **Anti-cheat (adaptive loop)**:
  1. Two independent adversarial batches — `adv_train` for training, `adv_eval`
     (never touched) for *every reported number*.
  2. Matched FPR before/after (recall bought by lowering threshold is not a gain).
  3. Regression check on the original attack distribution.

## Gap analysis (`evaluation/gap_analysis.py`)

Ten named evasion hypotheses, each with a predicate, the knob that exploits it,
and a remediation. Thresholds calibrated from the *legitimate* population so
"low value" means "indistinguishable from honest traffic".

| Key | Cause | Exploit knob |
|---|---|---|
| LOW_VALUE | Low-value amounts | amount_mult |
| SLOW_PACING | Slow / patient pacing | gap |
| FAMILIAR_DEVICE | Familiar device | p_new_device |
| FAMILIAR_GEOGRAPHY | Familiar geography | p_new_city |
| EXISTING_PAYEE | Existing beneficiary | p_reuse_existing_payee |
| MERCHANT_MIMICRY | Merchant mimicry | merchant_reuse |
| NO_CREDENTIAL_TRACE | No credential trace | p_credential_change |
| LOW_VELOCITY_FOOTPRINT | Low velocity footprint | n_drain |
| THIN_BUT_CLEAN_IDENTITY | Aged synthetic identity | identity_quality |
| SEQUENCE_ONLY | Visible only as a sequence | spread_days |

Two numbers per cause: `share_of_missed` (descriptive) and **`lift`** — how much
more common the trait is among misses than catches. 90% of misses *and* 90% of
catches explains nothing; lift is what the adversarial generator targets.

**Sample diagnosis from a real run:**

```
50 of 298 attacks evaded detection (recall 0.8322)

CAUSE                     %missed  %detected   lift  attribution
Familiar geography            90%        58%   1.56x         21%
Slow / patient pacing         72%        44%   1.65x         19%
Aged synthetic identity       98%        71%   1.38x         18%
Merchant mimicry              82%        58%   1.42x         16%

WEAKEST SEGMENT: TRANSACTION_MANIPULATION / HARD — 45.0% recall
```

## Why the numbers are trustworthy (methodology guards)

1. **Never evaluate on training attacks** — dual independent adversarial batches.
2. **Matched FPR** on the evaluation population.
3. **Regression check** — baseline performance reported beside the gain.
4. **Leakage audit** (`test_leakage_audit.py`): single-feature ROC-AUC for all 83
   features; anything > 0.99 fails; three real leaks were found and fixed this way.
5. **Causality proof** — bit-identical under truncation.
6. **Metrics known-answers** — hand-computed velocity windows, metric correctness
   against sk-learn reference values, TreeSHAP vs brute-force Shapley.

---

# 8. Developed Prototype — System Architecture

## Core loop (from README)

```
                    ┌─────────────────────────┐
                    │   FRAUD INTELLIGENCE    │  7 attack families
                    │   attack_taxonomy.json  │  parameterised, not scripted
                    └───────────┬─────────────┘
                                ▼
                    ┌─────────────────────────┐
                    │  SYNTHETIC DATA ENGINE  │  7 behavioural personas
                    │  customers / merchants  │  14 merchant categories
                    │  devices / transactions │  20 cities, habit modelling
                    └───────────┬─────────────┘
                                ▼
                    ┌─────────────────────────┐
                    │      RED TEAM AI        │  4 evasion skill levels
                    │  sequence generators    │  events, not single rows
                    └───────────┬─────────────┘
                                ▼
                    ┌─────────────────────────┐
                    │      BLUE TEAM AI       │  83 causal features
                    │  GBDT / RF + TreeSHAP   │  risk bands + reason codes
                    └───────────┬─────────────┘
                          ┌─────┴─────┐
                          ▼           ▼
                     DETECTED       MISSED
                          │           │
                          ▼           ▼
                    MITIGATION   ┌─────────────────────────┐
                                 │     GAP ANALYSIS        │  10 evasion
                                 │  why did it fail?       │  hypotheses, ranked
                                 └───────────┬─────────────┘  by attribution
                                             ▼
                                 ┌─────────────────────────┐
                                 │ ADVERSARIAL GENERATOR   │  auditable knob
                                 │ gap-directed attacks    │  moves + black-box
                                 └───────────┬─────────────┘  evasion search
                                             ▼
                                      RETRAIN / RETEST
                                             │
                                             └──────► LOOP
```

## Runtime topology (`python sg.py serve` → :8000)

```
                         ┌──────────────────────────────┐
  Browser ─────────────► │   SGServer (http.server)     │
                         │  - static Next.js dashboard  │
                         │  - REST API (JSON)           │
                         │  - SSE event streams         │
                         │  - async job registry        │
                         └──────┬───────┬──────┬────────┘
                                │       │      │
              ┌─────────────────┘       │      └─────────────────┐
              ▼                         ▼                      ▼
      AppState (in-memory)       SQLite Store             Snapshot
      world + trained detector   runs / jobs /            (pickle world
      + memoised caches          experiments artifacts    + Detector files)
```

- **`AppState`** holds a built world (population tables, transaction stream,
  attack batch) and a trained detector (`Detector.save/load`).
- **Boot seeding**: `serve` loads `data/snapshot/` — the world and a trained
  detector reload in **seconds** and pre-warm the cache, so the dashboard opens
  fully populated instead of a ~2 min cold build+train. Regenerate with
  `python sg.py snapshot --scale demo`.
- **Memoisation**: `/api/detect` and `/api/gap` are cached per `(run, detector)` —
  "New simulation" is only expensive for genuinely new parameters.
- **Async jobs + SSE**: heavy operations (simulate, red-team generate, loop) run
  as jobs (202/JOB_CREATED → job id) with `generation | progress | done` named SSE
  events. Client disconnects are swallowed silently (browsers abort constantly).

## REST API surface

- **GET**: `/api/health`, `/api/config`, `/api/taxonomy`, `/api/taxonomy/{type}`,
  `/api/runs`, `/api/runs/{id}`, `/api/gap`, `/api/loop/latest`, `/api/models`,
  `/api/experiments`, `/api/experiments/{id}`, `/api/jobs/{id}`, `/api/sse/{id}`.
- **POST**: `/api/simulate`, `/api/redteam/generate`, `/api/detect`, `/api/score`,
  `/api/attacks`, `/api/search`, `/api/attack`, `/api/gap`, `/api/loop`.

## Frontend (Next.js 14, plain JS/JSX, 9 views)

Overview · Studio · Red Team · Blue Team · Explainability (TreeSHAP waterfall) ·
Live · Intelligence (taxonomy) · Gap Analysis · Adaptive Loop.
The SSE client subscribes with named-event listeners (`addEventListener`) because
the backend streams **named** events; `onmessage` would silently ignore them.

## CLI (`sg.py`) — one command, all capability

`demo` (full loop) · `snapshot --scale demo` · `build`/`train`/`redteam`/`gap`/
`loop`/`experiments`/`taxonomy` · `serve`.
**Docker**: `docker compose up backend | up | run --rm demo | run --rm experiments`.
**Verify**: `python verify.py --quick` (~90 s) and `--full` (demo scale ~15 min) —
14 asserting stages: env, tests, world, redteam, blueteam, explain, risk, gap,
loop, audit, api, store, cli, frontend.

---

# 9. Scalable System Architecture & Design Concepts

## Current design (single node) — what it already does well

| Property | How today's prototype satisfies it |
|---|---|
| **Correctness** | Schema contracts with asserts; tests that *assert* (not just run); leakage/causality proofs |
| **Reproducibility** | Single `RunConfig` (seed + scale + attack types + difficulty mix) → config-fingerprint caching |
| **Reliability** | SQLite in a state dir (avoids network-mount lock bugs); Store falls back to tmp; snapshot boot is atomic & fast |
| **Testability** | Hermetic temp-stores for API tests — no live-server contention |
| **Operability** | Clean logs (client disconnects silent by design); `SG_*` env overrides; `--list`/`--stage`/`--skip` verification |
| **Deployability** | Zero-install core; `docker compose` for the whole stack |

## Target design (scale-out) — a growth path, not a rewrite

```
                    ┌────────────── Load Balancer / API Gateway ───────────────┐
                    │                                                          │
        ┌───────────▼──────────┐        ┌───────────▼──────────┐   ┌───────────▼──────────┐
        │    WEB / UI tier     │        │      API tier        │   │   Auth / rate-limit  │
        │ Next.js (stateless)  │        │ http.server / FastAPI│   │                      │
        └───────────┬──────────┘        └───────┬───▲──────────┘   └──────────────────────┘
                    │                            │   │ (async results)
                    ▼                            ▼   │
             SSE / WebSocket                  ┌─────────┴─────────┐
             gateway                          │   JOB QUEUE        │
                                             │   (redis/rabbit)    │
                                             └─────┬──────┬───────┘
                    ┌────────────────────────┬──────┘      └────────┬─────────────────────┐
                    ▼                        ▼                      ▼                     ▼
        ┌──────────────────┐   ┌────────────────────┐   ┌──────────────────┐  ┌──────────────────┐
        │ GENERATION workers│   │ FEATURE workers     │   │ TRAINING workers │  │  INFERENCE (serving)│
        │ (horizontal by    │   │ (partition by       │   │ (GBDT/RF on GPU/ │  │  stateless model   │
        │  customer_id)     │   │  customer_id)       │   │  or CPU, version)│  │  endpoint+registry │
        └─────────┬────────┘   └─────────┬──────────┘   └─────────┬────────┘  └─────────┬────────┘
                  └──────────┬──────────┴───────────┬─────────────┴────────────────────┘
                             ▼                      ▼                         ▼
                    ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
                    │  PostgreSQL      │   │ Object storage   │   │ Model registry + │
                    │  (DDL shipped)   │   │  (snapshots,     │   │  artefacts (S3/  │
                    │  partitioned     │   │   CSVs, JSON)    │   │  versioned)      │
                    └──────────────────┘   └──────────────────┘   └──────────────────┘
```

## How each system-design concept is handled

### Feasibility
- Core runs on `numpy`+`pandas` only — trivially portable to any VM/container.
- Every piece of the target arch maps to code that already exists: Postgres DDL,
  job registry, artefact store, model save/load, memoised API.
- SQLite→PostgreSQL is a connection swap, not a query rewrite.

### Maintainability
- **Single source of truth** per concern: `config.py` (all constants),
  `schema.py` (contracts + leakage guard), `attack_taxonomy.json` (attacks),
  `RunConfig` (reproducibility fingerprint).
- **Assertions everywhere**: features assert no label columns; API returns 400/404
  not 500s; explain asserts local accuracy at runtime.
- **Tests assert properties**, and expensive mistakes are caught by cheap schema
  tests first.
- Structured output: `FEATURE_LABELS` keeps explanations human, so the UI never
  drifts from the model contract.

### Scalability
- **Stateless tiers** scale horizontally (UI, API, inference).
- **Splittable batch work**: world generation, feature building and training are
  embarrassingly parallel by `customer_id`/fold; the loop already separates
  `adv_train`/`adv_eval` batches (natural shard boundaries).
- **Async everywhere** — the job/SSE pattern is exactly how a queue-backed worker
  pool behaves; the dashboard already tolerates long jobs.
- **Caching** — memoisation is today's cache; a Redis layer would drop in behind
  the same keys `(run, detector)`.
- **Scale profiles** (nano→full, 300→100k customers) are a built-in load test.

### Other quality attributes
- **Availability**: multi-replica stateless tiers + queue durability + snapshot
  restore path.
- **Security**: synthetic-only data, no real PII; CORS/OPTIONS handled; auth/
  rate-limit tier in the gateway.
- **Performance**: histogram binning + subsampling bound training cost; snapshot
  boot (~seconds) removes the cold-start; memoisation bounds repeated calls.
- **Cost**: from-scratch numpy models are CPU-friendly (no GPU dependency for
  lab-scale runs); the queue allows burst work to be spread over idle workers.

## Trade-offs (honest)

| Choice | Cost | Mitigation |
|---|---|---|
| From-scratch ML | Less infra complexity, but no battle-tested library | Verified against theoretical bounds + reference backends when present |
| Single-process serve | Not horizontally scalable as-is | Stateless design means a queue split is mechanical |
| prototype risk thresholds | Not production policy | Documented as tunable; bands are configuration |
| synthetic data ≠ reality | Absolute metrics won't transfer | Relative before/after comparisons are the transferable result |
| per-transaction scoring | MULTI_STAGE only visible as sequence | Graph/sequence features + planned sequence model |

---

# 10. Data Flow Diagram (Current)

## End-to-end, from generator to dashboard

```
      SOURCES                                          BUILD & FEATURES
 ┌───────────────────────┐                    ┌──────────────────────────────────┐
 │ attack_taxonomy.json  │                    │  merge legit + attack events     │
 │ config.py (personas,  │   ┌───────────┐    │  sort by (timestamp, txn_id)     │
 │  categories, cities)  │──►│ build_world│──►│  build_features()  — one pass,   │
 │ SEED / RunConfig      │   └───────────┘    │  STRICT causality (pre-t only)   │
 └───────────────────────┘                    │  → DataFrame[FEATURE_COLUMNS]    │
                        │                     └──────────────┬───────────────────┘
                        ▼                                    ▼
 ┌───────────────────────┐                    ┌───────────────────────────────┐
 │  users (dashboard,    │                    │  SPLIT (temporal,             │
 │  CLI, experiments)    │                    │   campaign-grouped)           │
 └──────────┬────────────┘                    │   train / validation / test   │
            │                                 └───────┬───────────┬───────────┘
            ▼                                         ▼           ▼
 ┌──────────────────────┐                 ┌────────────────────────────┐
 │  REST API / SSE      │                 │  TRAIN GBDT / RF           │
 │  (http.server)       │                 │  threshold at FPR budget   │
 └──────────┬───────────┘                 └──────────────┬─────────────┘
            │                                            ▼
            │                              ┌────────────────────────────┐
            │                              │  SCORE test + batch        │
            │                              │  → risk band + TreeSHAP    │
            │                              └──────┬──────────┬──────────┘
            │                                     ▼          ▼
            │                            ┌────────────────────────────┐
            │                            │  MISSED? → GAP ANALYSIS    │
            │                            │  (10 hypotheses, lift)     │
            │                            └──────┬─────────────────────┘
            │                                   ▼
            │                   ┌────────────────────────────┐
            │                   │  ADVERSARIAL GENERATOR       │
            │                   │  knob moves + black-box      │
            │                   │  evasion search              │
            │                   └──────┬──────────┬────────────┘
            │                          ▼          ▼
            │                adv_train batch   adv_eval batch
            │                 ┌──────────────┐   │ (never trained on)
            │                 │ RETRAIN +    │◄──┘
            │                 │ RETEST       │
            │                 └──────┬───────┘
            ▼                        ▼
 ┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
 │  STORE (SQLite)      │   │  ARTEFACTS            │   │  DASHBOARD           │
 │  runs · jobs ·       │   │  experiments/results/ │   │  Next.js 9 views     │
 │  loop history        │   │  (*.json)             │   │  + snapshot boot     │
 └──────────────────────┘   │  snapshot/ (pickle)   │   └──────────────────────┘
                            └──────────────────────┘
```

## Key data artefacts

| Artefact | Format | Producer → Consumer |
|---|---|---|
| Attack taxonomy | JSON | taxonomy → Red Team / UI |
| Synthetic CSVs | CSV | build → features / inspection |
| Feature matrix | pandas DataFrame | features → split → training / scoring |
| Trained detector | pickle (`Detector.save/load`) | training → serve / snapshot |
| Snapshot world | pickle | build → boot seeding |
| Run records | SQLite rows | pipeline → API / UI |
| Experiment results | JSON | `experiments/` → deck / analysis |
| Reports (gap, diversity, recall-by-segment) | JSON | evaluation → API/UI |

---

# 11. ML Architecture — Data Collection to Training

## From raw events to a trained, guarded detector

```
        DATA COLLECTION (synthetic, no real PII)
        ────────────────────────────────────────
        build_population (personas, merchants, devices, cities)
                 │
                 ▼
        generate_legitimate_transactions (hour curves, LEGIT_EVENT_RATES)
                 │
                 ▼
        RedTeam.generate(attack_types, difficulty_mix, n)
                 │   (sequences spliced into victim timelines)
                 ▼
        MERGED EVENT STREAM  (EVENT_COLUMNS = 26)
                 │
                 ▼
        FEATURE ENGINEERING  build_features() — ONE STREAMING PASS
                 │   strict causality: emits row t BEFORE appending row t to history
                 │   → FEATURE_COLUMNS = 83  (LABEL_COLUMNS excluded, asserted)
                 ▼
        FEATURE MATRIX  X (n × 83)   +   y (fraud_label)   +   campaign meta
                 │
   ┌─────────────┴───────────────────────────────────┐
   │                                                 │
   ▼                                                 ▼
 TEMPORAL SPLIT                                SPLIT GUARD
 (earliest window → train)   ──────────────►   campaign-grouped: every attack_id
 validation / test windows                      entirely in one split (tested)
   │
   ▼
 THRESHOLD POLICY                              VALIDATION SET
 choose highest-recall threshold               (legit FPR ≤ budget, default 1%)
 whose FPR on legit ≤ budget                   ──► threshold T
   │
   ▼
 TRAINING (from-scratch GBDT)
 ┌───────────────────────────────────────────────┐
 │ histogram binning → split search on histograms│
 │ logistic loss + second-order (Newton) gain    │
 │ row/column subsampling per iteration          │
 │ early stopping on validation loss             │
 │ (Random Forest: same tree builder, bagged)    │
 └───────────────┬───────────────────────────────┘
                 ▼
 EVALUATION      ROC-AUC · PR-AUC · recall at T · precision
                 bootstrap CIs · recall by (attack type, difficulty, persona)
                 │
                 ▼
 EXPLAINABILITY  TreeSHAP (verified vs brute-force Shapley)
                 local accuracy asserted; FEATURE_LABELS → reason codes
                 │
                 ▼
 GAP ANALYSIS    10 hypotheses × (share_of_missed, lift) → attribution %
                 │
                 ▼
 ADVERSARIAL BATCH   knob moves (ADVERSARIAL_MOVES) + black-box evasion search
                 │
     ┌───────────┴────────────┐
     ▼                        ▼
  adv_train batch          adv_eval batch
     │                      (held out — never touches training)
     ▼
 RETRAIN + RETEST           AT MATCHED FPR
     │                      + regression check (baseline distribution)
     ▼
  PROVEN IMPROVEMENT or      └──► loop again
  surfaced trade-off
```

## Guardrails wired into the architecture

| Guardrail | Test / mechanism |
|---|---|
| No label leak into features | `test_no_label_column_is_a_feature`, `test_event_and_label_columns_disjoint` |
| No feature is an oracle | `test_no_single_feature_is_a_label_oracle` (single-feature AUC ≤ 0.99 for all 83) |
| Causality is structural | `test_causality_under_truncation` (bit-identical at 25/50/75%) |
| No campaign leakage across splits | verify harness (`redteam`/`blueteam`/`loop` stages) |
| Honest customers do suspicious things | `test_legitimate_traffic_has_low_but_nonzero_risk_events` |
| No training/eval overlap in the loop | dual independent `adv_train`/`adv_eval` RNG streams |
| Metric correctness | known-answers against sk-learn reference metrics |
| Explanation correctness | `test_treeshap_matches_brute_force_shapley` (2.7e-08) |

## The classifier is not the product

The trained GBDT/RF is only one block. The *system* — features under a causality
contract, gap-directed adversarial generation, matched-FPR retest with a regression
check — is what converts a model into a **self-auditing improvement loop**.

---

# 12. Future Scope

## In progress / next sprint
- **13-family GenAI-native taxonomy** (DEEPFAKE_ATO, CONVERSATIONAL_AGENT,
  AGENTIC_APP, DEEPFAKE_KYC, MULE_NETWORK, INVOICE_TIMED_BEC) with per-family
  generators and evidence-cited entries.
- **GenAI defence signals** — new event/feature columns (voice-verification
  authenticity, liveness confidence, agent-session anomaly, KYC-check confidence,
  mule-relay graph score, invoice-pattern match), each with non-zero legitimate
  rates, re-audited for leakage and re-verified for causality.
- **Emergence experiment** — train on classic families only, zero-shot evaluate on
  never-seen GenAI families; then adaptive-loop improvement on the held-out batch.

## Product roadmap
- **Mixed-ratio adversarial retraining** — blend adversarial and baseline attacks
  at a fixed ratio during retraining to eliminate the −11.1 pt baseline regression.
- **Sequence / graph models** — score the account *timeline*, not only the row
  (the structural blind spot for MULTI_STAGE); beneficiary-network graph features.
- **Cost-sensitive thresholds** — optimise on actual fraud loss vs false-positive
  cost rather than a single FPR budget.
- **Real-data calibration** — validate transferability against a public or de-identified
  transaction dataset; compare our synthetic distributions to it.
- **Wider evasion search** — expand beyond the current knob space; add an LLM-based
  variant explorer that proposes novel sequences and lets the black-box scorer rank them.
- **Real-time streaming detector** — online scoring at the payment switch, with
  continuous model versioning and canary deployment behind the model registry.
- **Media-authenticity fusion** — pipe liveness/voice-verification outcomes into the
  feature layer so layered defence is demonstrated end-to-end.
- **Federated playbooks** — share parameterised attack profiles across institutions
  without sharing raw data (the taxonomy format is already privacy-safe).

## Expansion target map

| Current | Target |
|---|---|
| 7 attack families | 13 (6 GenAI-native) |
| 83 features / 26 event columns | ~95 / ~36 with GenAI signals |
| Per-transaction scoring | + sequence & graph layers |
| Single batch loop | Streamed, federated loop |
| SQLite | PostgreSQL partitions (+ queue, object storage, model registry) |
| Threshold by FPR | Cost-aware optimisation |

---

# 13. Challenges We Faced

## 1. Air-gapped environment → rebuild the ML stack from scratch
No network access meant XGBoost, LightGBM, `shap` and FastAPI were unavailable.
Rather than stub them out, we implemented a **histogram GBDT, Random Forest and
path-dependent TreeSHAP in pure numpy**. The risk of shipping unverified custom ML
was mitigated by correctness proofs: 98.6% of a known Bayes-optimal AUC, and
TreeSHAP agreement of 2.7e-08 against brute-force enumeration of the definition.

## 2. Label leakage — found and fixed *by* the system's own audit
Three genuine leaks, all caught by `test_no_single_feature_is_a_label_oracle`
(single-feature AUC > 0.99), all now pinned by regression tests:

1. **`device_reputation` oracle.** Attacker-created devices were given reputation
   0.12. The model learned "low reputation ⇒ fraud" — but a real bank cannot know a
   device belongs to an attacker the first time it appears. *(Fixed: attacker
   devices draw from the same reputation distribution.)*
2. **Registration-event leak.** After the fix, newly-registered devices were drawn
   from `Beta(2,3)` while the existing registry used `Beta(7.5,1.7)` — the
   *registration event itself* still separated the classes (avg 0.41 vs 0.80).
3. **Footprint oracle.** Synthetic identities had `digital_footprint_days` in a
   range that barely overlapped honest customers (**AUC 1.000**), and *no* honest
   customer had a genuinely new account. *(Fixed: footprint expressed as a ratio of
   account age; 12% of honest customers are recent signups.)*

4. **Timing leak.** All attacks anchored at the victim's *last* transaction, so
   fraud piled up at the end of the stream and the temporal split trained on almost
   no positives. *(Fixed: attacks spread over the victim's history.)*

## 3. Causality — enforced structurally, then proven
The naive approach (groupby/rolling on the full series) peeks forward. We enforce
causality by appending history only *after* a row's features are emitted, and prove
it with the truncation test (bit-identical output at 25/50/75% truncation).

## 4. Campaign leakage across splits
Random train/test shuffling splits a 10-event takeover across both sets and lets the
model see a customer's future. Splits are temporal **and campaign-grouped** — every
`attack_id` lands entirely in one split, enforced by the verify harness.

## 5. "Honest customers do suspicious things"
The single most important design decision. If any legit rate (new device, travel,
new payee) were zero, the corresponding flag becomes a perfect fraud oracle and all
metrics become meaningless. Non-zero rates in `LEGIT_EVENT_RATES` are guarded by a
dedicated test.

## 6. The adaptation dilemma — honest negatives
Adversarial hardening *worked* (+13.5 pts recall on a held-out adversarial batch at
matched FPR) but **regressed baseline recall by 11.1 pts**. The easy path was to
hide it; we report both numbers, because surfacing exactly this trade-off is the
purpose of the tool. Mixed-ratio retraining is the planned fix.

## 7. Aggregate metrics hide who pays
The 1% FPR budget was met overall while **persona FPR spanned 0.46%–1.46% (3.2×)**.
Which segment is worst changes between runs — the disparity is driven by history
sparsity × operating point, not a fixed property of a group. A model tuned only on
aggregate FPR would ship this unexamined.

## 8. Rarity drives alert noise, not model quality
Same architecture: precision 0.33 at 1% prevalence vs 0.78 at 5%. Recall barely rose
above a 1% budget while precision halved — so the tight budget was the better
operating point. Any "maximise recall" objective would have chosen badly. We report
**no accuracy** and pick thresholds by FPR budget.

## 9. Engineering constraints near the frontend
- **Next.js dev proxy caps upstream responses at 30 s** → heavy operations became
  async jobs (202 + job id) with streaming SSE. Browsers abort connections
  constantly → client-disconnect exceptions are swallowed by design (a clean log
  is a feature, not a bug).
- **No `next build` in the original build environment** → the frontend was verified
  statically (all imports/exports and **134 API field references** checked against
  live responses); later `npm run build` and visual/responsive checks run separately.
- **Dashboard/model drift**: an unversioned feature-change could silently change UI
  columns → `FEATURE_LABELS` + schema tests keep the contract, and API tests use
  hermetic temp-stores so tests never fight a live server over one sqlite file.

## 10. Reproducibility & size
- Everything must reproduce from `seed 20260823` + a scale profile; heavy results
  ship as JSON artefacts with environment config so the docs cannot drift.
- Snapshot files get large (a 100k-customer world is hundreds of MB) → snapshot is
  the *reboot* path, regenerated on demand, and never committed needlessly.

---

# Appendix A — Headline Metrics

## Experiment 1 — Baseline (nano: 300 customers, 21 days, leak-corrected pipeline)

| Prevalence | Model | Recall | Precision | F1 | ROC-AUC | PR-AUC | FPR |
|---|---|---|---|---|---|---|---|
| 1.0% | GBDT | 0.6111 | 0.3333 | 0.4314 | 0.9534 | 0.4914 | 1.08% |
| 1.0% | Random Forest | 0.6296 | 0.4146 | 0.5000 | 0.9652 | 0.4712 | 0.78% |
| 5.0% | GBDT | 0.7884 | 0.7778 | 0.7831 | 0.9824 | 0.8579 | 1.07% |
| 5.0% | Random Forest | 0.6519 | 0.8197 | 0.7262 | 0.9757 | 0.8013 | 0.68% |

## Experiment 3 — Transfer to unseen families

| Held out | Unseen recall | Unseen ROC-AUC | Seen recall (same window) | Retention |
|---|---|---|---|---|
| Transaction Manipulation | 0.5517 | 0.9238 | 0.8615 | **64%** |
| Synthetic Identity + Merchant Fraud | 0.2697 | 0.8826 | 0.6267 | 43% |
| Social Engineering + Multi-Stage | 0.3099 | 0.9125 | 0.7654 | 40% |

## Experiment 4 — Adversarial vs ordinary synthetic fraud

| Attack population | Recall | Precision |
|---|---|---|
| Ordinary synthetic fraud | 0.5897 | 0.4299 |
| Gap-directed adversarial | **0.2561** | 0.9326 |
| **Recall drop** | **−33.4 pts** | |

## Experiment 5 — Adaptive training (the headline)

| | Recall | F1 | Attacks missed | FPR |
|---|---|---|---|---|
| Before hardening | 0.2201 | 0.3567 | 2,863 | 0.991% |
| After hardening | **0.3552** | **0.5189** | **2,367** | 0.991% |
| **Change** | **+13.5 pts** | **+16.2 pts** | −496 | *matched* |
| Regression (baseline distribution) | 0.5139 → 0.4028 (***−11.1 pts***) | | | |

## Experiment 6 — FPR budget sweep

| FPR budget | Realised | Recall | Precision | Alerts / 1k good txns |
|---|---|---|---|---|
| 0.1% | 0.196% | 0.5000 | 0.6923 | 1.96 |
| 0.2% | 0.212% | 0.5000 | 0.6750 | 2.12 |
| 0.5% | 0.521% | 0.5370 | 0.4754 | 5.21 |
| 1.0% | 0.929% | 0.6111 | 0.3667 | 9.29 |
| 2.0% | 1.988% | 0.6296 | 0.2179 | 19.88 |
| 5.0% | 5.247% | 0.7407 | 0.1105 | 52.47 |

## Correctness proofs

| Proof | Result |
|---|---|
| GBDT vs Bayes-optimal AUC | 0.8842 vs 0.8969 → **98.6%** of theoretical maximum |
| TreeSHAP vs brute-force Shapley | agreement **2.7e-08** absolute, flat across depths 2–6 |
| Causality under truncation | bit-identical at k = 25/50/75% |
| Leakage audit | all 83 single-feature AUCs ≤ 0.99 (3 leaks found & fixed historically) |

---

# Appendix B — Demo Script

1. **`python sg.py taxonomy`** — show the parameterised knowledge base (7 families →
   13 with GenAI-native entries and evidence).
2. **`python sg.py demo`** — the whole loop in one command: build world → red team →
   blue team → gap → adversarial → retest.
3. **`python sg.py serve`** — open the dashboard on :8000 (snapshot-booted, fully
   populated in seconds).
4. **Overview** — headline cards: adversarial recall 22.0→35.5% at matched FPR,
   83 features, 92 tests, leakage-audit badge.
5. **Studio / Red Team** — generate a new attack batch (async job + live SSE
   progress), inspect a scenario's stage sequence.
6. **Blue Team / Explain** — pick a fraud transaction; TreeSHAP waterfall shows the
   exact causal drivers and reason codes.
7. **Gap Analysis** — show the ten hypotheses ranked by lift; click through to the
   weakest segment.
8. **Adaptive Loop** — run `loop -n 400`; show before/after on the *held-out*
   adversarial batch at matched FPR, plus the honest regression number.
9. **Verify** — `python verify.py --quick` (or 14-stage list) as evidence the
   pipeline *asserts* correctness, then `python tests/run_tests.py` for the 92-test
   suite, then `cd frontend && npm run build`.
10. **Close** — future scope: 13 GenAI families, GenAI defence signals, emergence
    experiment, sequence/graph model, mixed-ratio retraining.

---

*Prepared for the AI Defense Lab for Payment Security hackathon. All figures are
from the leak-corrected pipeline; experiment JSON artefacts live in
`experiments/results/` so this document can never drift from the measurements.*