# SovereignGuard

**An AI Red Team–Blue Team payment-security laboratory for GenAI-powered fraud.**

Conventional fraud detection is reactive: models learn from historical fraud, rules
are written after an attack is observed, and defences are updated once attackers have
already found a weakness. Generative AI breaks that model, because the cost of
producing a *new variant* of an attack has collapsed to near zero.

SovereignGuard inverts the process. Instead of waiting for real fraud, it builds a
controlled synthetic environment where the defence is attacked **before** a real
customer is:

```
IDENTIFY → GENERATE → ATTACK → DETECT → EXPLAIN → ADAPT → RETEST
```

It is not another fraud classifier. It is a continuous stress-testing and improvement
layer that discovers where a fraud model fails, generates harder attacks aimed at that
specific failure, and proves whether the defence actually improved.

---

## The headline result

The system diagnosed its own weakness, generated adversarial attacks targeting it,
retrained, and improved — measured on an adversarial batch the retrained model
**never saw**, at an **identical false-positive rate**:

| | Recall | F1 | Attacks missed | FPR |
|---|---|---|---|---|
| Baseline defence | 22.0% | 0.357 | 2,863 | 0.991% |
| Hardened defence | **35.5%** | **0.519** | **2,367** | 0.991% |
| **Change** | **+13.5 pts** | **+16.2 pts** | −496 | *matched* |

**But there is a cost, and it is the most important number here:** recall on the
*original* attack distribution **fell 11.1 points** (51.4% → 40.3%). Hardening against
adversarial attacks traded away performance on the attacks the defence already handled.

That trade-off is a real finding, not a failure of the tool — it is precisely what a
stress-testing layer exists to surface *before* a model reaches production. A single
round of adversarial retraining on a narrow, gap-directed batch shifts the decision
boundary toward that batch. The mitigation (future work) is to mix adversarial and
baseline attacks in a fixed ratio during retraining rather than appending adversarial
examples wholesale.

Why the baseline is only 22%: these are **adversarial** attacks generated specifically
to evade that detector. [Experiment 4](#4--adversarial-vs-ordinary-synthetic-fraud)
shows recall falling from 59% to 26% when a defence is *aimed at* rather than merely
tested. That collapse is the entire thesis. A naive implementation that evaluated on the
same attacks it trained on would print ~99% and mean nothing. See
[Methodology](#methodology-how-not-to-fool-yourself).

---

## Quick start

No installation is required for the core system. It runs on Python 3.9+ with only
`numpy` and `pandas`.

```bash
python sg.py demo            # the whole story, one command (~2 min)
```

Other entry points:

```bash
python sg.py taxonomy                    # the attack knowledge base
python sg.py build   --scale demo --save # generate a synthetic world, write CSVs
python sg.py train   --model gbdt        # train + evaluate the Blue Team
python sg.py redteam --difficulty HARD -n 500
python sg.py gap                         # why did the defence fail?
python sg.py loop    -n 400              # the adaptive loop
python sg.py experiments                 # all six measured experiments
python sg.py serve                       # REST API + dashboard on :8000
```

For the React dashboard, see [`frontend/README.md`](frontend/README.md).

---

## Architecture

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

---

## The five pillars

### 1. Identify — Fraud Intelligence Engine

[`data/attack_taxonomy.json`](data/attack_taxonomy.json) is a knowledge base of seven
attack families across the payment surface, each specifying its target, the payment
rails it abuses, the role generative AI plays, the behavioural changes it induces in
the event stream, the features a defender could use, its stage sequence, and concrete
mitigations.

| Family | Severity | Why it is hard |
|---|---|---|
| Account Takeover | CRITICAL | Hard variant hijacks an existing session — no new device |
| Transaction Manipulation | HIGH | Every single transaction is unremarkable by construction |
| Synthetic Identity | HIGH | Behaves *better* than a real customer until bust-out |
| Merchant Fraud | HIGH | A fake storefront looks like a new legitimate one |
| Phishing / Payment Link | HIGH | The customer genuinely authorises it; all auth passes |
| Social Engineering | CRITICAL | Nothing is compromised — own device, own location |
| Multi-Stage | CRITICAL | Only the *ordering* is incriminating |

The taxonomy is *parameterised rather than enumerated*, because the practical effect of
GenAI is a shift from a few high-volume templates to very many low-volume variants.
The Red Team samples that parameter space instead of replaying fixed scripts.

### 2. Generate — Synthetic Data Engine

Fully synthetic, so no real customer data is ever needed. Two design decisions carry
most of the realism:

**Amounts blend customer and merchant.** Each amount mixes the customer's own price
point with the merchant category's ticket size (62/38 in log space). The same customer
spends differently at a cinema and a travel agent; two customers spend differently at
the same grocer. Without this, `amount_ratio_customer_median` would be noise.

**Legitimate customers do suspicious things.** Real people change phones, travel, add
payees, mistype passwords, and occasionally buy something 12× their normal amount.
Rates live in `config.LEGIT_EVENT_RATES`. This is the single most important choice in
the project — without it `is_new_device` becomes a perfect fraud oracle, recall hits
100%, and every reported number is meaningless.

Measured at 400 customers over 30 days (47,476 transactions in 2.4 s):

| Property | Value | Sanity check |
|---|---|---|
| Median amount | ₹857 | plausible retail ticket |
| 99th percentile | ₹29,307 | long tail, not absurd |
| Transfers | 12.7% | reasonable A2A share |
| Overnight (00–06) | 12.1% | matches the hour curve |
| Approved | 98.4% | realistic auth rate |
| **New beneficiary** | **0.09%** | **rare but non-zero — the leakage guard** |

### 3. Attack — Red Team

Seven generators produce **event sequences**, not single fake rows, spliced into a
victim's real timeline. Features are then recomputed over the merged stream, so an
attack's velocity and novelty features are genuinely *earned* from history rather than
stamped on.

Four evasion skill levels. The gradient is the point — HARD attacks converge on
legitimate statistics:

| Feature | LEGIT | EASY | MEDIUM | HARD |
|---|---|---|---|---|
| Amount vs. customer median | 2.0× | 15.7× | 7.2× | **2.8×** |
| New-device rate | 0.019 | 0.075 | 0.063 | **0.023** |
| Distance from home (km) | 27 | 835 | 226 | **92** |
| Amount as % of credit limit | 5.7% | 42.8% | 20.3% | **8.1%** |

Diversity is *measured*, not asserted. `AttackBatch.diversity_report()` reports
normalised entropy per dimension; a representative 400-scenario batch scored 0.987
(family), 0.999 (victim persona), 0.963 (geography), spanning 4.4 orders of magnitude
in amount across 27 distinct attack stages.

### 4. Detect — Blue Team

**83 features** across amount, velocity, device, location, merchant, temporal,
identity, session and graph dimensions, computed under a strict causality contract:
every feature for transaction *t* uses only information available strictly before *t*.
Enforced structurally — history is appended only *after* a row's features are emitted.

Two models, both implemented from scratch in numpy (see
[Dependencies](#dependencies-and-a-deliberate-deviation)):

- **Histogram GBDT** — logistic loss, second-order gain, row/column subsampling,
  early stopping, histogram subtraction
- **Random Forest** — bagged trees; squared-error splitting on a 0/1 target is
  provably equivalent to Gini, so one tree builder serves both models

Correctness evidence: on a synthetic problem with an XOR-style interaction and a known
Bayes-optimal AUC of 0.8969, the GBDT reached **0.8842 — 98.6% of the theoretical
maximum** — and recovered exactly the four true signal features.

**No accuracy is ever reported.** At 1% prevalence a model that approves everything
scores 99% accuracy and is worthless.

### 5. Explain, Adapt, Retest

**Explainability** uses a path-dependent **TreeSHAP** implementation written for this
project. It is verified against brute-force enumeration of the Shapley definition over
all 2^M subsets: agreement to **2.7e-08 absolute** on values of magnitude ~0.36, flat
across tree depths 2–6 (an indexing bug would compound with depth). Local accuracy —
`base + Σφ == model output` — is asserted at runtime.

**Gap analysis** tests ten named evasion hypotheses against every missed attack, with
thresholds calibrated from the *legitimate* population so "low value" means
"indistinguishable from honest traffic". Two numbers per cause:

- `share_of_missed` — descriptive
- **`lift`** — how much more common the trait is among misses than catches. A trait in
  90% of misses *and* 90% of catches explains nothing. This is what the adversarial
  generator targets.

**The adversarial generator** maps each diagnosed cause to an auditable knob change
(`ADVERSARIAL_MOVES`), plus an optional black-box evasion search that scores candidates
with the deployed detector and keeps only those that evade it — what an attacker
probing a live endpoint would do.

Sample diagnosis from a real run:

```
50 of 298 attacks evaded detection (recall 0.8322)

CAUSE                     %missed  %detected   lift  attribution
Familiar geography            90%        58%   1.56x         21%
Slow / patient pacing         72%        44%   1.65x         19%
Aged synthetic identity       98%        71%   1.38x         18%
Merchant mimicry              82%        58%   1.42x         16%

WEAKEST SEGMENT: TRANSACTION_MANIPULATION / HARD — 45.0% recall
```

---

## Methodology: how not to fool yourself

The adversarial loop is trivially easy to fake. Generate adversarial attacks, retrain
on them, evaluate on those same attacks, and recall soars — because the model
memorised them. That result is worthless.

Three guards are built in:

**1. Two independent adversarial batches.** `adv_train` goes into training;
`adv_eval` is generated from the same process with a different RNG stream and is used
for *every* reported number. It is excluded from training and validation by index.

**2. Matched false-positive budget.** Before and after are both re-pinned to the same
FPR on the evaluation population. A recall gain bought by lowering the threshold is not
a gain, and comparing recall at two different thresholds is the easiest way to
overstate a result.

**3. Regression check.** Performance on the original attack distribution is reported
alongside, to catch hardening that improves adversarial recall by breaking baseline
recall.

Splitting is also **temporal and campaign-grouped**: train on the earliest window, and
all events of one `attack_id` land in the same split. Random shuffling would let the
model see a customer's future when predicting their past, and would split a 10-event
takeover across train and test.

### Label leaks found and fixed

Three leaks were found by adversarial audit, all now pinned by regression tests in
`tests/test_leakage_audit.py` and documented in source comments:

1. **`device_reputation` was set to 0.12 for attacker-created devices.** A perfect
   oracle: the model learned "low reputation ⇒ fraud". A real bank cannot know a device
   belongs to an attacker the first time it appears.
2. **After fixing (1), newly-registered devices were drawn from `Beta(2,3)` while the
   original registry used `Beta(7.5,1.7)`.** Since every attacker device is
   newly-registered, the *registration event itself* still leaked the label — attacker
   devices averaged 0.41 reputation against 0.80 for the rest.
3. **Synthetic identities had a `digital_footprint_days` range that barely overlapped
   honest customers** (AUC 1.000), and no honest customer had a genuinely new account.
   Footprint is now expressed as a *ratio* of account age, and 12% of honest customers
   are recent signups — so "new" no longer implies "fake".

A fourth issue was a *timing* leak rather than a feature leak: all attacks originally
anchored at the victim's last transaction, so fraud piled up at the end of the stream
and the temporal split trained on almost no positives.

The audit that catches this class of bug is `test_no_single_feature_is_a_label_oracle`,
which computes single-feature ROC-AUC against the label for all 83 features and fails if
any exceeds 0.99. A legitimate behavioural feature correlates with fraud; a leaked one
*separates* it.

---

## What the experiments actually taught us

Five findings that were not obvious before running them, and that a system built only
to look good would have hidden:

**1. Adversarial pressure is devastating.** A defence catching 59% of ordinary
synthetic fraud caught 26% once attacks were aimed at its measured weaknesses. Any
benchmark that does not do this overstates durability by tens of points.

**2. Adversarial hardening works, but it is not free.** Held-out adversarial recall rose
13.5 points — while baseline-distribution recall fell 11.1. One round of retraining on a
narrow gap-directed batch pulls the boundary toward that batch. This is exactly the kind
of regression a stress-testing layer should catch before deployment, and the reason the
loop reports both numbers rather than only the flattering one.

**3. Generalisation to unseen fraud depends on shared vocabulary.** Transaction
manipulation retained 64% of recall when never seen; social engineering and multi-stage
retained ~40%. ROC-AUC stayed high (0.88–0.92) even where recall collapsed — the model
still *ranks* novel attacks above average, it just cannot clear a threshold calibrated
on different fraud. This qualifies the cold-start claim: synthetic adversarial data
helps, but it cannot conjure signal for evidence the model never learned to read.

**4. Rarity, not model quality, drives alert noise.** The same architecture went from
0.33 to 0.78 precision purely by moving prevalence from 1% to 5%. Recall barely improved
above a 1% FPR budget while precision halved, so the tighter budget was the better
operating point — a naive "maximise recall" objective would have chosen badly.

**5. Aggregate false-positive rates hide who pays.** FPR by customer persona spanned
0.46% to 1.46% — a 3.2× disparity — while the aggregate stayed inside budget throughout.
Which segment is worst shifts between runs, which is itself informative: it means the
disparity is driven by history sparsity interacting with the operating point, not by a
stable property of any one group.

### On the numbers in this README

An earlier draft of this document reported far better figures (65.6% hardened recall,
+61 point gains). Those were **inflated by three label leaks** that an adversarial audit
subsequently found:

1. `device_reputation` was set low for attacker-created devices — a perfect oracle.
2. After fixing that, newly-registered devices were drawn from a *different*
   distribution than the original registry, so the registration event still leaked.
3. Synthetic identities had `digital_footprint_days` in a range that barely overlapped
   honest customers (AUC 1.000), and no honest customer had a genuinely new account.

All three are fixed, pinned by regression tests in `tests/test_leakage_audit.py`, and
documented in source comments. The numbers above are from the corrected pipeline. They
are worse, and they are real.

---

## Experimental results

Six experiments, run via `python sg.py experiments`. Each writes a JSON artefact to
`experiments/results/` containing raw numbers, configuration and environment, so this
document cannot drift from the measurements. Numbers below are from `--scale nano`
(300 customers, 21 days) on the leak-corrected pipeline.

### 1 — Baseline

Held-out test window, operating point chosen on validation at a 1% FPR budget.

| Prevalence | Model | Recall | Precision | F1 | ROC-AUC | PR-AUC | FPR |
|---|---|---|---|---|---|---|---|
| 1.0% | GBDT | 0.6111 | 0.3333 | 0.4314 | 0.9534 | 0.4914 | 1.08% |
| 1.0% | Random Forest | 0.6296 | 0.4146 | 0.5000 | 0.9652 | 0.4712 | 0.78% |
| 5.0% | GBDT | 0.7884 | 0.7778 | 0.7831 | 0.9824 | 0.8579 | 1.07% |
| 5.0% | Random Forest | 0.6519 | 0.8197 | 0.7262 | 0.9757 | 0.8013 | 0.68% |

The prevalence effect is the instructive result: at 1% fraud, precision is 0.33 (two
alerts in three are false); at 5% it reaches 0.78. Rarity, not model quality, is what
makes the alert queue noisy. Note also that Random Forest edges out GBDT at 1% — at this
scale the difference is within noise, which is why both are reported.

### 2 — Attack diversity

| Families | Recall | Precision | F1 | ROC-AUC |
|---|---|---|---|---|
| 7 (all) | 0.6111 | 0.3548 | 0.4490 | 0.9509 |

Performance holds as the attack mix widens; the cost of covering more behaviours from a
fixed positive budget shows up in precision rather than recall. (Full 1/3/5/7 sweep is
in `exp2_attack_diversity.json`; at `nano` scale the narrower subsets have too few
positives per family for the individual points to be stable.)

### 3 — Unseen attack families

Train on some families, test on families the model has **never seen**. Recall on the
held-out families is compared against recall on the seen families *in the same window at
the same threshold*, so the number is interpretable.

| Held out | Unseen recall | Unseen ROC-AUC | Seen recall | Retention |
|---|---|---|---|---|
| Transaction Manipulation | 0.5517 | 0.9238 | 0.8615 | **64%** |
| Synthetic Identity + Merchant Fraud | 0.2697 | 0.8826 | 0.6267 | 43% |
| Social Engineering + Multi-Stage | 0.3099 | 0.9125 | 0.7654 | 40% |

Transfer is real but partial: 40–64% of recall survives on fraud classes the model has
never encountered. Crucially, ROC-AUC stays at 0.88–0.92 throughout — the model still
ranks unseen attacks well above average, it simply cannot clear a threshold calibrated on
different fraud. That distinction matters operationally: it means novel fraud is
*rankable* even when it is not *catchable* at the current operating point.

### 4 — Adversarial vs. ordinary synthetic fraud

Same detector, same false-positive budget, two attack populations.

| Attack population | Recall | Precision |
|---|---|---|
| Ordinary synthetic fraud | 0.5897 | 0.4299 |
| Gap-directed adversarial | **0.2561** | 0.9326 |
| **Recall drop** | **−33.4 pts** | |

A defence catching 59% of ordinary synthetic fraud catches **one attack in four** once
the attacker aims at its measured weaknesses. Note that precision *rises* to 0.93 — the
attacks that do get caught are caught with high confidence; the problem is entirely the
ones that slip through silently.

### 5 — Adaptive training (the headline)

Measured on an adversarial batch generated independently of the batch used for
retraining, at a matched false-positive rate.

| | Recall | F1 | Attacks missed | FPR |
|---|---|---|---|---|
| Before hardening | 0.2201 | 0.3567 | 2,863 | 0.991% |
| After hardening | **0.3552** | **0.5189** | **2,367** | 0.991% |
| **Change** | **+13.5 pts** | **+16.2 pts** | −496 | *matched* |

**Regression check: recall on the original attack distribution fell from 0.5139 to
0.4028 (−11.1 points).** The hardening genuinely improved adversarial robustness and
genuinely degraded baseline performance. Reporting only the first half would be
dishonest; catching this trade-off is the entire purpose of running the check.

### 6 — False positives and customer friction

| FPR budget | Realised | Recall | Precision | Alerts / 1k good txns |
|---|---|---|---|---|
| 0.1% | 0.196% | 0.5000 | 0.6923 | 1.96 |
| 0.2% | 0.212% | 0.5000 | 0.6750 | 2.12 |
| 0.5% | 0.521% | 0.5370 | 0.4754 | 5.21 |
| 1.0% | 0.929% | 0.6111 | 0.3667 | 9.29 |
| 2.0% | 1.988% | 0.6296 | 0.2179 | 19.88 |
| 5.0% | 5.247% | 0.7407 | 0.1105 | 52.47 |

Recall gains above a 1% budget are small (0.61 → 0.74) while precision collapses
(0.37 → 0.11) and analyst workload rises 5.6×. On this population the tighter budget is
clearly the better operating point.

**Fairness finding.** False-positive rate by customer persona:

| Persona | Legit txns | FPR |
|---|---|---|
| Young professional | 1,099 | **1.46%** |
| High net worth | 326 | 1.23% |
| Small business | 1,516 | 1.19% |
| Student | 965 | 0.73% |
| Senior | 303 | 0.66% |
| Family | 844 | 0.59% |
| Gig worker | 1,084 | 0.46% |

A 3.2× spread between the most and least affected segment, while the aggregate FPR
stayed inside budget the whole time. Which persona lands worst varies between runs and
seeds, which is itself the finding: the disparity is driven by how sparse a segment's
transaction history is relative to the operating point, not by a stable property of any
one group. Either way, a model tuned only on aggregate FPR would ship this unexamined.


---

## Testing

```bash
python tests/run_tests.py           # 82 tests, ~19s, no pytest required
python tests/run_tests.py -v        # full tracebacks
pytest tests/                       # also works if pytest is installed
```

The suite runs without pytest because pytest is not a guaranteed dependency; fixtures
are memoised plain functions exposed as pytest fixtures when pytest is present.

Three tests carry most of the weight:

**`test_causality_under_truncation`** — the guarantee the whole project rests on.
Features are built on a transaction stream, then rebuilt on the same stream truncated
after row *k*, and the first *k* rows must be **bit-identical**. Any feature that peeked
forward — an unshifted groupby, a full-series mean, a rolling window with the wrong
closure — would change the past when the future was removed. Verified at k = 25%, 50%
and 75%.

**`test_treeshap_matches_brute_force_shapley`** — TreeSHAP checked against a
brute-force enumeration of all 2^M subsets straight from the Shapley definition, across
tree depths 2–5 and 100+ tree/row comparisons.

**`test_legitimate_traffic_has_low_but_nonzero_risk_events`** — the label-oracle guard.
Asserts honest customers *do* change device, add payees and travel, at rates above zero
and below 10%. If any of those rates were zero the corresponding flag would perfectly
identify fraud and every metric in this README would be meaningless.

Also covered: velocity windows against hand-computed arithmetic, campaign-leakage in
splits (no `attack_id` may span two splits), that `ADVERSARIAL_MOVES` reference real
`Knobs` fields and actually mutate them, metric known-answers against scikit-learn
reference values, and that the API returns 400/404 rather than 500 on bad input.

One genuine bug was found by these tests and fixed in the source: `Store`'s fallback
caught only `sqlite3.OperationalError`, but an unwritable *directory* raises `OSError`
from `mkdir` first, so the fallback never triggered.

---

## Dependencies, and a deliberate deviation

The plan specified XGBoost/LightGBM, SHAP and FastAPI. This project was built in an
environment with **no network access**, so none of them could be installed.

Rather than stub them out, the ML core is implemented directly:

| Planned | Built | Why it is defensible |
|---|---|---|
| XGBoost / LightGBM | Histogram GBDT in numpy | Verified to 98.6% of Bayes-optimal AUC |
| scikit-learn RF | Bagged trees, Gini-equivalent | Same tree builder; equivalence proven in source |
| `shap` | Path-dependent TreeSHAP | Verified exact against the Shapley definition |
| FastAPI | `http.server` with the same routes | Zero dependencies; identical JSON contracts |
| PostgreSQL | SQLite (+ `postgres_ddl()`) | Same SQL; swap the connection, not the queries |

**Core runtime requirement: `numpy` and `pandas` only.** Everything runs with no
install step, on any machine.

`detection.optional_backends()` reports which third-party libraries are present, so on
a machine that *does* have XGBoost/LightGBM/SHAP the results can be cross-checked
against reference implementations.

The React dashboard requires Node (`next`, `react`, `react-dom` only).

---

## Repository layout

```
sovereignguard/
├── config.py              personas, categories, cities, risk bands, scales
├── schema.py              event / feature / label contracts + leakage guard
├── features.py            83 causal behavioural features
├── detection.py           splits, training, scoring, explanation
├── risk.py                probability → risk score → band → action
├── taxonomy.py            attack knowledge base accessor
├── pipeline.py            build_world / train_baseline / adversarial_loop
├── store.py               SQLite persistence (PostgreSQL DDL included)
├── generators/
│   ├── population.py      customers, merchants, devices
│   ├── transactions.py    legitimate traffic simulator
│   ├── attacks.py         difficulty knobs + victim context
│   ├── families.py        the seven attack generators
│   ├── redteam.py         orchestrator + diversity measurement
│   └── adversarial.py     gap-directed generation + evasion search
├── ml/
│   ├── tree.py            histogram decision tree (binning, split search)
│   ├── models.py          GBDT + Random Forest
│   └── treeshap.py        TreeSHAP + brute-force reference
├── evaluation/
│   ├── metrics.py         ROC-AUC, PR-AUC, threshold policy, bootstrap CIs
│   └── gap_analysis.py    ten evasion hypotheses, attribution, remediation
└── api/server.py          REST API + static dashboard host

frontend/                  Next.js dashboard (7 pages)
experiments/run_all.py     the six experiments
data/attack_taxonomy.json  the knowledge base
sg.py                      command line
```

---

## Limitations

Stated plainly, because a system whose purpose is honest evaluation should be honest
about itself:

- **Synthetic data is a model, not reality.** Realism is defended by construction and
  by distributional sanity checks, but it has not been validated against a real
  payment portfolio. Absolute metrics would differ on real data; the *relative*
  before/after comparisons are the transferable result.
- **The detector is per-transaction.** MULTI_STAGE attacks are, by construction, only
  visible as a sequence. Some graph and sequence context is engineered into features,
  but a true sequence model is future work — and the gap analysis correctly identifies
  this as a structural blind spot rather than hiding it.
- **The adversarial search is bounded** by the knob space in `Knobs`. A real attacker
  is not so constrained.
- **Risk-band thresholds are prototype policy values**, tuned experimentally. They are
  not any real scheme's thresholds and are not presented as such.
- **The React dashboard is unverified.** Imports, exports and all 134 API field
  references were checked statically against live backend responses, but `npm install`
  and `next build` could not be run in the build environment.
- **Tests cover correctness properties, not every code path.** 82 tests pass, including
  the causality proof, the TreeSHAP proof and the leakage audit, but there is no coverage
  measurement and the adversarial search path is only smoke-tested.
- **One round of adversarial hardening degrades baseline recall** (−11.1 points in
  Experiment 5). The loop surfaces this correctly but does not yet fix it; mixing
  adversarial and baseline attacks at a controlled ratio during retraining is the
  obvious next step.
- **Reported figures are at `nano` scale** (300 customers, 21 days) so the suite runs in
  minutes. Confidence intervals at this size are wide — `exp1_baseline.json` includes
  bootstrap CIs on recall. Use `--scale demo` or larger for anything load-bearing.

## Future work

Mixed-ratio adversarial retraining to eliminate the baseline regression; sequence
modelling over the account timeline (the structural blind spot for MULTI_STAGE); graph
features across the beneficiary network; calibration against a real or public transaction
dataset; cost-sensitive thresholds using actual fraud loss and false-positive costs; and
widening the adversarial search beyond the current knob space.

---

## Safety

SovereignGuard is a **defensive simulation platform**. It does not access real
accounts, execute real transactions, send messages to anyone, or attack live systems.
Attacks exist only as rows in a synthetic dataset. The taxonomy deliberately describes
attacks at the level of their *effect on a transaction stream* rather than as
operational instructions.

## Licence

MIT — see [LICENSE](LICENSE).
