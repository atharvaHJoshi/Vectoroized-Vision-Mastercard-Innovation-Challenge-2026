# SovereignGuard — Complete Technical Documentation

> AI Red Team / Blue Team Payment-Security Laboratory  
> MasterCard Hackathon 2026

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [Architecture](#3-architecture)
4. [Directory Structure](#4-directory-structure)
5. [Configuration System](#5-configuration-system)
6. [Data Schema](#6-data-schema)
7. [Synthetic Data Engine](#7-synthetic-data-engine)
8. [Feature Engineering](#8-feature-engineering)
9. [Machine Learning Core](#9-machine-learning-core)
10. [Red Team — Attack Generation](#10-red-team--attack-generation)
11. [Blue Team — Detection](#11-blue-team--detection)
12. [Risk Decision Engine](#12-risk-decision-engine)
13. [Explainability (TreeSHAP)](#13-explainability-treeshap)
14. [Gap Analysis](#14-gap-analysis)
15. [Adaptive Attack/Defence Loop](#15-adaptive-attackdefence-loop)
16. [REST API](#16-rest-api)
17. [Frontend Dashboard](#17-frontend-dashboard)
18. [CLI Reference](#18-cli-reference)
19. [Docker Deployment](#19-docker-deployment)
20. [Verification & Testing](#20-verification--testing)
21. [Experiments](#21-experiments)
22. [Critical Design Decisions](#22-critical-design-decisions)

---

## 1. Project Overview

SovereignGuard is a self-contained synthetic payment-fraud testing lab. It generates a realistic simulated payment ecosystem — customers, merchants, devices, legitimate transactions, and injected fraud — then pits an AI Red Team against an AI Blue Team in an adversarial loop.

**What it does:**
1. Builds a synthetic payment world with configurable scale (300 to 100,000 customers)
2. Generates realistic legitimate transaction streams with behavioural features
3. Injects 7 families of fraud attacks at 4 difficulty levels
4. Trains a gradient-boosted decision tree (GBDT) detector from scratch in numpy
5. Measures detection quality at a fixed false-positive budget (never accuracy)
6. Explains every decision via TreeSHAP
7. Identifies why attacks evade detection (10 evasion hypotheses)
8. Generates harder attacks targeted at diagnosed weaknesses
9. Retrains and re-measures on a held-out adversarial batch
10. Serves everything through a REST API and a Next.js dashboard

**Key constraint:** All ML (GBDT, Random Forest, TreeSHAP) is implemented from scratch in numpy. No XGBoost, LightGBM, or sklearn dependency.

---

## 2. Tech Stack

### Backend (Python)
| Component | Technology | Version |
|---|---|---|
| Language | Python | 3.9+ (tested on 3.14.7) |
| Numerical core | numpy | ≥1.21 (tested 2.5.2) |
| Data manipulation | pandas | ≥1.3 (tested 3.0.5) |
| GBDT classifier | Custom (numpy) | histogram-based, 64 bins |
| Random Forest | Custom (numpy) | bootstrap + column subsampling |
| TreeSHAP | Custom (numpy) | path-dependent, verified vs brute-force |
| REST API | stdlib `http.server` | no FastAPI, no Flask |
| Persistence | SQLite | via stdlib `sqlite3` |
| Optional | xgboost, lightgbm, sklearn, shap | for cross-validation only |

### Frontend (JavaScript)
| Component | Technology | Version |
|---|---|---|
| Framework | Next.js | 14.2.35 |
| UI Library | React | 18.3.1 |
| Language | Plain JS/JSX | no TypeScript |
| CSS | Plain CSS | 589-line dark-theme design system |
| Charts | Hand-drawn SVG | no recharts, no chart.js, no d3 |
| HTTP client | fetch API | native browser |
| Package count | 3 | next, react, react-dom |

### Infrastructure
| Component | Technology |
|---|---|
| Container | Docker (python:3.11-slim-bookworm) |
| Orchestration | docker-compose (5 services) |
| Database | SQLite (file-based, named volume in Docker) |
| State directory | `~/.local/state/sovereignguard/` |

---

## 3. Architecture

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js :3000)                     │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │Overview │ │Red Team  │ │Blue Team │ │ Adaptive │  ...       │
│  │  View   │ │  View    │ │  View    │ │  Loop    │           │
│  └────┬────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│       └───────────┴────────────┴─────────────┘                 │
│                        │  fetch()                               │
│                   /api/*  proxy (next.config.js)                │
└────────────────────────┼────────────────────────────────────────┘
                         │
┌────────────────────────┼────────────────────────────────────────┐
│              Backend (Python :8000)                              │
│  ┌─────────────────────┴──────────────────────────┐            │
│  │            API Server (http.server)              │            │
│  │  18 routes: GET/POST /api/*                     │            │
│  └──────┬──────────┬──────────┬──────────┬────────┘            │
│         │          │          │          │                       │
│  ┌──────┴───┐ ┌────┴────┐ ┌──┴───┐ ┌───┴──────┐              │
│  │  Build   │ │  Train  │ │ Gap  │ │ Adaptive │              │
│  │  World   │ │ Baseline│ │Analysis│ │   Loop   │              │
│  └──────┬───┘ └────┬────┘ └──┬───┘ └───┬──────┘              │
│         │          │          │          │                       │
│  ┌──────┴──────────┴──────────┴──────────┴──────────┐          │
│  │                  Core Library                     │          │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │          │
│  │  │Generators│ │   ML     │ │   Evaluation     │ │          │
│  │  │ pop/txn/ │ │ tree/    │ │   metrics/       │ │          │
│  │  │ attacks/ │ │ models/  │ │   gap_analysis   │ │          │
│  │  │ families │ │ treeshap │ │                   │ │          │
│  │  └──────────┘ └──────────┘ └──────────────────┘ │          │
│  └──────────────────────────────────────────────────┘          │
│         │                                                       │
│  ┌──────┴──────────────────────────────────────────┐          │
│  │              SQLite (sovereignguard.db)          │          │
│  │  tables: runs, customers, merchants, devices,   │          │
│  │          transactions, attacks, models, loops    │          │
│  └─────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
build_world()
    │
    ├─→ build_population()    → customers, merchants, devices
    ├─→ generate_legit()      → legitimate transactions (streaming, causal)
    ├─→ build_features()      → 83-feature matrix (strict causality)
    ├─→ inject_attacks()      → fraud events spliced into timelines
    │
    ▼
train_baseline()
    │
    ├─→ temporal_grouped_split()  → train / validation / test (no campaign leakage)
    ├─→ train_detector()          → GBDT model (numpy from scratch)
    ├─→ score_test()              → predictions + risk scores
    │
    ▼
diagnose()
    │
    ├─→ compute_metrics()         → recall, precision, F1, ROC-AUC, PR-AUC
    ├─→ analyse_gaps()            → 10 evasion hypotheses, attribution
    │
    ▼
adversarial_loop()
    │
    ├─→ adapt_knobs()             → targeted knob changes from gap analysis
    ├─→ AdversarialGenerator      → harder attacks at diagnosed weaknesses
    ├─→ search()                  → black-box evasion search (optional)
    ├─→ retrain on adv_train      → hardened model
    ├─→ evaluate on adv_eval      → held-out adversarial batch
    │
    ▼
REST API ──→ Frontend Dashboard
```

---

## 4. Directory Structure

```
sovereign-guard-2026/
├── sg.py                          # CLI entry point
├── verify.py                      # End-to-end verification (14 stages)
├── requirements.txt               # numpy>=1.21, pandas>=1.3
├── requirements-optional.txt      # xgboost, lightgbm, sklearn, shap, etc.
├── Dockerfile                     # Python 3.11-slim-bookworm
├── docker-compose.yml             # 5 services
├── LICENSE                        # MIT
├── AGENTS.md                      # Agent instruction file
│
├── sovereignguard/                # Core Python library
│   ├── __init__.py
│   ├── config.py                  # All constants, scales, personas, categories
│   ├── schema.py                  # FEATURE_COLUMNS (83), LABEL_COLUMNS (7), contracts
│   ├── rng.py                     # Reproducible per-component RNG
│   ├── store.py                   # SQLite persistence
│   ├── risk.py                    # RiskEngine: probability → band → action
│   ├── taxonomy.py                # Attack taxonomy loader
│   ├── pipeline.py                # build_world, train_baseline, adversarial_loop
│   ├── features.py                # 83 causal features, streaming computation
│   ├── detection.py               # Detector, splits, training, scoring
│   │
│   ├── generators/                # Synthetic data generators
│   │   ├── population.py          # Customers, merchants, devices
│   │   ├── transactions.py        # Legitimate transaction stream
│   │   ├── attacks.py             # Knobs, VictimContext, shared helpers
│   │   ├── families.py            # 7 attack family generators
│   │   ├── redteam.py             # RedTeam orchestrator
│   │   └── adversarial.py         # Adaptive adversarial generation
│   │
│   ├── ml/                        # Machine learning (from scratch)
│   │   ├── tree.py                # Binner, Tree, TreeBuilder (histogram)
│   │   ├── models.py              # GBDT, Random Forest, sigmoid, logloss
│   │   └── treeshap.py            # Path-dependent TreeSHAP + brute-force
│   │
│   ├── evaluation/                # Metrics and analysis
│   │   ├── metrics.py             # ROC-AUC, PR-AUC, operating curve, bootstrap
│   │   └── gap_analysis.py        # 10 evasion hypotheses, attribution
│   │
│   └── api/
│       └── server.py              # REST API (18 routes, stdlib http.server)
│
├── data/
│   ├── attack_taxonomy.json       # 7-family attack knowledge base
│   └── synthetic/                 # Generated synthetic data (after build)
│
├── models/                        # Saved model artefacts
├── experiments/
│   ├── run_all.py                 # 6 experiments
│   └── results/                   # JSON experiment results
│
├── tests/
│   ├── run_tests.py               # Custom test runner (82 tests)
│   ├── conftest.py                # Fixtures (seed=20260823)
│   ├── test_schema.py
│   ├── test_features.py
│   ├── test_generators.py
│   ├── test_detection_api.py
│   ├── test_leakage_audit.py
│   ├── test_metrics_risk.py
│   └── test_ml.py
│
└── frontend/                      # Next.js 14 dashboard
    ├── package.json               # 3 dependencies
    ├── next.config.js             # API proxy to :8000
    ├── pages/
    │   ├── _app.jsx               # globals.css import (only location)
    │   └── index.jsx              # App shell, sidebar, shared state
    ├── views/
    │   ├── Overview.jsx           # Situation room
    │   ├── Intelligence.jsx       # Attack taxonomy browser
    │   ├── RedTeam.jsx            # Attack simulator
    │   ├── BlueTeam.jsx           # Detection results
    │   ├── Explain.jsx            # TreeSHAP explainability
    │   ├── GapAnalysis.jsx        # Evasion hypothesis report
    │   └── AdaptiveLoop.jsx       # Hero adaptive loop
    ├── components/
    │   ├── UI.jsx                 # Kpi, Card, Table, Badge, etc.
    │   └── Charts.jsx             # 8 SVG chart components
    ├── lib/
    │   └── api.js                 # API client + formatters
    └── styles/
        └── globals.css            # 589-line dark-theme design system
```

---

## 5. Configuration System

All constants live in `sovereignguard/config.py`.

### Scale Profiles

| Scale | Customers | Merchants | Days | Attacks/Type | ~Transactions |
|---|---|---|---|---|---|
| `nano` | 300 | 200 | 21 | 80 | ~16,000 |
| `tiny` | 400 | 300 | 30 | 120 | ~31,000 |
| `demo` | 2,000 | 1,200 | 45 | 400 | ~234,000 |
| `large` | 10,000 | 4,000 | 60 | 1,200 | ~1,560,000 |
| `full` | 100,000 | 20,000 | 90 | 4,000 | ~23,400,000 |

Approximate transactions = `n_customers × n_days × 2.6`

### Personas (7)

| Persona | Weight | Age | Amount μ (log) | Amount σ | Txns/Day | Night Activity | Travel |
|---|---|---|---|---|---|---|---|
| STUDENT | 16% | 18–25 | 5.55 | 0.80 | 3.4 | 17% | 22% |
| YOUNG_PROFESSIONAL | 22% | 24–34 | 6.55 | 0.92 | 4.1 | 11% | 34% |
| FAMILY | 21% | 32–50 | 7.05 | 0.88 | 3.0 | 5% | 28% |
| SENIOR | 12% | 58–78 | 6.85 | 0.72 | 1.3 | 2% | 14% |
| GIG_WORKER | 11% | 21–40 | 5.95 | 0.85 | 5.6 | 21% | 18% |
| SMALL_BUSINESS | 10% | 28–55 | 8.10 | 1.05 | 7.8 | 9% | 40% |
| HIGH_NET_WORTH | 8% | 35–65 | 8.95 | 1.20 | 2.6 | 8% | 62% |

Each persona has distinct: `method_weights` (UPI/CARD/WALLET/NETBANKING), `category_affinity` (14 merchant categories), `new_merchant_rate`, `device_change_rate`, `transfer_share`.

### Merchant Categories (14)

| Category | Weight | Base Ticket (log) | Intrinsic Risk | CNP Share |
|---|---|---|---|---|
| FOOD | 14% | 5.85 | 0.10 | 55% |
| GROCERY | 13% | 6.55 | 0.07 | 30% |
| ECOMMERCE | 12% | 6.90 | 0.28 | 98% |
| MOBILITY | 9% | 5.30 | 0.12 | 90% |
| UTILITIES | 9% | 6.75 | 0.05 | 85% |
| FUEL | 8% | 6.45 | 0.09 | 15% |
| ENTERTAINMENT | 7% | 5.95 | 0.16 | 80% |
| P2P_TRANSFER | 7% | 7.30 | 0.34 | 100% |
| TRAVEL | 6% | 8.40 | 0.22 | 92% |
| HEALTHCARE | 5% | 7.10 | 0.08 | 35% |
| EDUCATION | 4% | 8.05 | 0.07 | 70% |
| GAMING | 3% | 5.70 | 0.42 | 100% |
| FINANCIAL_SERVICES | 2% | 8.60 | 0.30 | 95% |
| CRYPTO_GATEWAY | 1% | 8.20 | 0.72 | 100% |

### Cities (20)

18 Indian cities + Dubai + Singapore. Each has `(latitude, longitude, population_weight)`.  
High-risk locations: `["Dubai", "Singapore", "Guwahati", "Lucknow"]`

### Risk Bands

| Band | Range | Action | Description |
|---|---|---|---|
| LOW | 0–30 | ALLOW | Approve straight through |
| MEDIUM | 30–60 | MONITOR | Approve, log for behavioural monitoring |
| HIGH | 60–80 | STEP_UP_AUTH | Challenge with step-up authentication |
| CRITICAL | 80–100 | HOLD_REVIEW | Hold and route to fraud analyst queue |

### Legitimate Event Rates (non-zero by design)

```python
{
    "password_change_per_year": 0.85,
    "profile_change_per_year": 1.6,
    "new_beneficiary_per_year": 5.2,
    "failed_login_burst_per_year": 3.1,
    "large_purchase_share": 0.021,
    "device_reinstall_per_year": 1.4,
}
```

These rates are deliberately non-zero. If any rate were 0, the corresponding feature would become a perfect fraud oracle, making all metrics meaningless.

### RunConfig

```python
@dataclass
class RunConfig:
    scale: str = "demo"                  # Scale profile name
    seed: int = 20260823                 # RNG seed
    attack_types: List[str]              # All 7 by default
    difficulty_mix: Dict[str, float]     # {"EASY": 0.25, "MEDIUM": 0.40, "HARD": 0.35}
    target_fpr: float = 0.010            # 1% false-positive budget
```

---

## 6. Data Schema

### Transaction Columns (26 raw fields)

```python
EVENT_COLUMNS = [
    "transaction_id", "customer_id", "merchant_id", "timestamp",
    "amount", "payment_method", "channel", "transaction_type",
    "device_id", "city", "lat", "lon", "beneficiary_id",
    "auth_result", "mcc_category", "session_id",
    # Behavioural / session context:
    "password_changed_recently", "profile_changed_recently",
    "failed_logins_1h", "session_duration_s", "typing_cadence_dev",
    "ip_asn_type", "is_new_beneficiary", "beneficiary_age_seconds",
    "sim_swapped_recently", "inbound_call_active", "payment_link_referred",
]
```

### Label Columns (7)

```python
LABEL_COLUMNS = [
    "fraud_label",       # 0 or 1
    "attack_type",       # e.g. "TRANSACTION_MANIPULATION" or "NONE"
    "attack_id",         # unique per attack campaign
    "attack_stage",      # e.g. "STRUCTURE", "DRAIN"
    "difficulty",        # "EASY", "MEDIUM", "HARD", "ADVERSARIAL"
    "generator",         # which function created it
    "campaign_id",       # groups related attacks
]
```

### Feature Contract

- `FEATURE_COLUMNS` (83) and `LABEL_COLUMNS` (7) must never overlap
- Any feature with single-feature AUC > 0.99 against the label is a leak
- Three historical leaks were found and fixed:
  1. `device_reputation` — was computed using future fraud labels
  2. `device_registration_distribution` — leaked device registration timing
  3. `digital_footprint_days` — was derived from attack injection timestamps

---

## 7. Synthetic Data Engine

### Workflow

```
build_population(scale, seed)
    │
    ├─→ Customers (n_customers)
    │     Each customer: persona, age, city, credit_limit, median_amount,
    │     amount_sigma, txns_per_day, n_devices, preferred_method,
    │     night_activity, travel_propensity, new_merchant_rate, etc.
    │
    ├─→ Merchants (n_merchants)
    │     Each merchant: category, city, intrinsic_risk, cnp_share,
    │     chargeback_rate, median_ticket, daily_volume, onboarded_via
    │
    └─→ Devices
          Each device: owner, os_family, device_class, is_emulator,
          is_rooted, reputation, first_seen_day

generate_legitimate_transactions(customers, merchants, devices, n_days, seed)
    │
    ├─→ Streaming: one customer at a time, one day at a time
    ├─→ Poisson arrival process per customer (λ = txns_per_day)
    ├─→ Amount sampled from log-normal(μ, σ) per persona
    ├─→ Merchant selected by category affinity × city proximity
    ├─→ Session context generated: typing cadence, session duration,
    │   IP type, failed logins, password/profile changes
    │
    └─→ Output: transaction DataFrame (26 columns)

build_features(transactions, customers, merchants, devices)
    │
    ├─→ Streaming: row by row, customer by customer
    ├─→ History APPENDED only after each row's features are emitted
    ├─→ 83 features across 12 groups
    │
    └─→ Output: feature DataFrame (83 columns, same row count)
```

### Key Design: Causality

Features for row *t* use only data before *t*. The test `test_causality_under_truncation` verifies bit-identical output when the transaction stream is truncated at 25%, 50%, 75%.

---

## 8. Feature Engineering

83 features across 12 groups, all computed with strict causal enforcement.

### Feature Groups

#### Amount Features (9)
| # | Feature | Description |
|---|---|---|
| 1 | `amount` | Transaction amount |
| 2 | `amount_log` | Transaction amount (log) |
| 3 | `amount_ratio_customer_median` | Amount vs. customer's normal amount |
| 4 | `amount_zscore_customer` | Amount z-score against customer history |
| 5 | `amount_ratio_merchant_median` | Amount vs. merchant's typical ticket |
| 6 | `amount_ratio_max_7d` | Amount vs. customer's 7-day maximum |
| 7 | `amount_round_number` | Suspiciously round amount |
| 8 | `amount_pct_of_credit_limit` | Amount as share of credit limit |
| 9 | `amount_ratio_p95_30d` | Amount vs. customer's 30-day 95th percentile |

#### Velocity Features (13)
| # | Feature | Description |
|---|---|---|
| 10 | `txns_last_10min` | Transactions in the last 10 minutes |
| 11 | `txns_last_1h` | Transactions in the last hour |
| 12 | `txns_last_24h` | Transactions in the last 24 hours |
| 13 | `txns_last_7d` | Transactions in the last 7 days |
| 14 | `amount_sum_1h` | Value transacted in the last hour |
| 15 | `amount_sum_24h` | Value transacted in the last 24 hours |
| 16 | `amount_sum_24h_ratio_median_day` | 24-hour value vs. normal daily value |
| 17 | `seconds_since_prev_txn` | Time since previous transaction |
| 18 | `distinct_merchants_24h` | Distinct merchants in 24 hours |
| 19 | `distinct_devices_24h` | Distinct devices in 24 hours |
| 20 | `distinct_cities_24h` | Distinct cities in 24 hours |
| 21 | `declines_last_24h` | Declined attempts in 24 hours |
| 22 | `escalating_amount_run` | Consecutive increasing-amount run |

#### Device Features (7)
| # | Feature | Description |
|---|---|---|
| 23 | `is_new_device` | First transaction from this device |
| 24 | `device_age_days` | Age of device on this account |
| 25 | `device_txn_count` | Prior transactions from this device |
| 26 | `device_share_of_customer` | Share of customer activity on this device |
| 27 | `is_emulator` | Device is an emulator |
| 28 | `is_rooted` | Device is rooted / jailbroken |
| 29 | `device_reputation` | Device reputation score |

#### Location Features (6)
| # | Feature | Description |
|---|---|---|
| 30 | `is_new_city` | First transaction from this city |
| 31 | `distance_from_home_km` | Distance from home city |
| 32 | `distance_from_prev_txn_km` | Distance from previous transaction |
| 33 | `implied_speed_kmh` | Implied travel speed since last transaction |
| 34 | `is_high_risk_location` | High-risk location |
| 35 | `city_txn_count` | Prior transactions in this city |

#### Merchant Features (8)
| # | Feature | Description |
|---|---|---|
| 36 | `is_new_merchant` | Never-before-seen merchant |
| 37 | `merchant_intrinsic_risk` | Merchant category risk |
| 38 | `merchant_age_days` | How long the merchant has existed |
| 39 | `merchant_chargeback_rate` | Merchant chargeback rate |
| 40 | `merchant_cnp_share` | Merchant card-not-present share |
| 41 | `merchant_daily_volume_log` | Merchant daily volume |
| 42 | `customer_merchant_txn_count` | Prior transactions with this merchant |
| 43 | `category_affinity_score` | Fit with customer's usual categories |

#### Temporal Features (6)
| # | Feature | Description |
|---|---|---|
| 44 | `hour_of_day` | Hour of day |
| 45 | `day_of_week` | Day of week |
| 46 | `is_night` | Overnight transaction |
| 47 | `is_weekend` | Weekend transaction |
| 48 | `hour_deviation_from_profile` | Hour differs from customer's pattern |
| 49 | `is_unusual_hour_for_customer` | Unusual hour for this customer |

#### Account / Identity Features (6)
| # | Feature | Description |
|---|---|---|
| 50 | `account_age_days` | Account age |
| 51 | `kyc_level_ord` | KYC verification level (0–3) |
| 52 | `identity_doc_score` | Identity document confidence |
| 53 | `contactability_score` | Contactability of the identity |
| 54 | `digital_footprint_days` | Age of the identity's digital footprint |
| 55 | `customer_lifetime_txns` | Customer's lifetime transaction count |

#### Session / Auth Features (12)
| # | Feature | Description |
|---|---|---|
| 56 | `password_changed_recently` | Password changed recently |
| 57 | `profile_changed_recently` | Profile details changed recently |
| 58 | `failed_logins_1h` | Failed logins in the last hour |
| 59 | `session_duration_s` | Session duration |
| 60 | `typing_cadence_dev` | Behavioural-biometric deviation |
| 61 | `ip_asn_is_hosting` | Traffic from hosting/datacentre IP |
| 62 | `ip_asn_is_vpn` | Traffic from VPN |
| 63 | `is_new_beneficiary` | Newly added beneficiary |
| 64 | `beneficiary_age_seconds` | Age of the beneficiary record |
| 65 | `sim_swapped_recently` | Recent SIM swap |
| 66 | `inbound_call_active` | Call in progress during payment |
| 67 | `payment_link_referred` | Payment started from an inbound link |

#### Method / Channel One-Hots (12)
| # | Feature | Description |
|---|---|---|
| 68–71 | `method_UPI`, `method_CARD`, `method_WALLET`, `method_NETBANKING` | Payment method |
| 72–75 | `channel_ECOM`, `channel_POS`, `channel_APP`, `channel_API` | Channel |
| 76–79 | `type_TRANSFER`, `type_WITHDRAWAL`, `type_PURCHASE`, `type_TOPUP` | Transaction type |

#### Sequence / Graph Features (4)
| # | Feature | Description |
|---|---|---|
| 80 | `seq_stage_index` | Position in the customer's recent action sequence |
| 81 | `customer_risk_events_24h` | Risk events on the account in 24 hours |
| 82 | `beneficiary_indegree_24h` | Distinct payers to this beneficiary in 24 hours |
| 83 | `merchant_new_customer_share_24h` | Merchant's share of first-time customers |

---

## 9. Machine Learning Core

All ML is implemented from scratch in numpy. No external ML libraries required.

### 9.1 Histogram Decision Tree (`ml/tree.py`)

#### `Binner`
```python
Binner(max_bins=64)
```
Discretises continuous features into histogram bins using quantile-based edges.

- `fit(X)` — learns bin edges from training data
- `transform(X)` — returns uint8 bin codes (1-indexed, bin 0 = missing)
- `n_bins` — returns `max_bins + 2` (includes missing bin and overflow)
- `bin_upper_value(feature, bin_idx)` — returns the upper bound for a specific bin

#### `Tree`
```python
@dataclass
class Tree:
    feature: np.ndarray      # int32; -1 for leaves
    threshold: np.ndarray    # uint8 bin index
    left: np.ndarray         # int32
    right: np.ndarray        # int32
    value: np.ndarray        # float32
    cover: np.ndarray        # float32
    n_nodes: int
```

- `predict_binned(Xb)` — vectorised level-by-level traversal
- `leaf_index(Xb)` — returns leaf node indices
- `max_depth_actual` — computed depth of the tree

#### `TreeBuilder`
```python
TreeBuilder(n_bins, max_depth=6, min_samples_leaf=20, min_child_weight=1e-3,
            l2=1.0, max_leaves=63, colsample=1.0, min_gain=1e-7)
```

- `build(cols, grad, hess, rows, rng)` — builds one tree from gradient/hessian pairs

### 9.2 Gradient Boosting (`ml/models.py`)

#### `GradientBoostingClassifier`
```python
GradientBoostingClassifier(
    n_estimators=200,       # Number of boosting rounds
    learning_rate=0.12,     # Shrinkage
    max_depth=6,            # Tree depth
    max_leaves=63,          # Max leaves per tree
    min_samples_leaf=20,    # Min samples in leaf
    min_child_weight=1e-3,  # Min hessian in leaf
    l2=1.0,                 # L2 regularisation
    subsample=0.8,          # Row subsampling
    colsample=0.7,          # Feature subsampling
    max_bins=64,            # Histogram bins
    early_stopping_rounds=25,  # Stop if no improvement
    scale_pos_weight=1.0,   # Class weight for fraud
    random_state=0,         # RNG seed
    verbose=False
)
```

**Methods:**
- `fit(X, y, eval_set=None, feature_names=None)` — trains the model
- `decision_function(X)` — returns logit (margin space)
- `predict_proba(X)` — returns `sigmoid(decision_function(X))`
- `feature_importances_(normalise=True)` — cover-weighted split count
- `importance_table(top=20)` — list of `(feature_name, importance)` tuples
- `save(path)` / `BaseModel.load(path)` — gzip JSON serialisation

**Training algorithm:**
1. Compute initial logit from class balance
2. For each round: compute gradient/hessian of log-loss
3. Build tree on gradient/hessian (histogram-based, column subsampled)
4. Update predictions with learning rate × tree output
5. Early stop if validation loss doesn't improve

#### `RandomForestClassifier`
```python
RandomForestClassifier(
    n_estimators=120, max_depth=14, min_samples_leaf=5,
    colsample=0.35, max_leaves=4096, bootstrap=True,
    subsample=1.0, max_bins=64, class_weight_balanced=True,
    random_state=0, verbose=False
)
```

- `fit(X, y)` — trains all trees
- `predict_proba(X)` — clipped mean of individual tree predictions
- `decision_function(X)` — logit of predict_proba

### 9.3 Model Comparison

| Property | GBDT | Random Forest |
|---|---|---|
| Training | Sequential boosting | Parallel bagging |
| Default trees | 200 | 120 |
| Default depth | 6 | 14 |
| Early stopping | Yes (25 rounds) | No |
| Class weighting | `scale_pos_weight` | `class_weight_balanced` |
| Subsampling | Row + column | Bootstrap + column |
| Typical recall | ~60% | ~55% |

---

## 10. Red Team — Attack Generation

### Attack Families (7)

| Family | Stages | Description |
|---|---|---|
| ACCOUNT_TAKEOVER | RECON_LOGIN → CREDENTIAL_CHANGE → PAYEE_ADD → PROBE → ESCALATE → DRAIN | Compromised credentials, drain through new payee |
| TRANSACTION_MANIPULATION | PROBE → CALIBRATE → STRUCTURE → REPEAT | Probe decision boundary, structure value beneath it |
| SYNTHETIC_IDENTITY | ONBOARD → CULTIVATE → LIMIT_GROWTH → BUST_OUT | Fabricated identity builds history, then busts out |
| MERCHANT_FRAUD | SEED_TRAFFIC → RAMP → CASH_OUT | Fake storefront takes volume from many payers |
| PHISHING_PAYMENT_LINK | AUTHORISE → SETTLE | Customer authorised a deceived payment |
| SOCIAL_ENGINEERING | PRETEXT → TRANSFER → REINFORCE | Victim coached through payment on live call |
| MULTI_STAGE | RECON → FOOTHOLD → MULE_PREP → TEST → FAN_OUT → CONSOLIDATE | Multi-step campaign with money mules |

### Evasion Skill Levels (4)

Each level has a `Knobs` dataclass controlling evasion parameters:

| Parameter | EASY | MEDIUM | HARD | ADVERSARIAL |
|---|---|---|---|---|
| `amount_mult_lo` | 12.0 | 4.0 | 1.4 | 0.9 |
| `amount_mult_hi` | 45.0 | 14.0 | 4.5 | 2.4 |
| `stay_under_p95` | False | False | True | True |
| `p_new_device` | 0.95 | 0.60 | 0.18 | 0.06 |
| `p_new_city` | 0.85 | 0.45 | 0.12 | 0.04 |
| `p_high_risk_city` | 0.55 | 0.20 | 0.04 | 0.01 |
| `p_hosting_ip` | 0.60 | 0.22 | 0.05 | 0.01 |
| `gap_lo_s` | 25 | 600 | 5,400 | 18,000 |
| `gap_hi_s` | 240 | 7,200 | 64,800 | 150,000 |
| `spread_days` | 1 | 2 | 6 | 12 |
| `n_drain_lo` | 3 | 2 | 3 | 4 |
| `n_drain_hi` | 7 | 5 | 9 | 12 |
| `p_probe` | 0.30 | 0.55 | 0.75 | 0.85 |
| `p_reuse_existing_payee` | 0.02 | 0.18 | 0.55 | 0.80 |
| `p_credential_change` | 0.90 | 0.55 | 0.20 | 0.06 |
| `p_round_amount` | 0.70 | 0.45 | 0.12 | 0.04 |

**Key insight:** HARD attacks deliberately mimic legitimate behaviour — low amounts, familiar devices/cities, existing payees, patient pacing.

### VictimContext

Each attack targets a specific victim with known behavioural patterns:

```python
@dataclass
class VictimContext:
    customer_id: str
    persona: str
    median_amount: float
    p95_amount: float
    max_amount: float
    credit_limit: float
    home_city: str
    home_lat/lon: float
    known_devices: List[str]
    known_merchants: List[str]
    known_categories: List[str]
    known_beneficiaries: List[str]
    preferred_method: str
    typical_hours: List[int]
    last_ts: int
    n_txns: int
```

### Diversity Measurement

After generation, diversity is measured via normalised entropy (1.0 = perfectly even, 0 = collapsed):
- Attack family entropy
- Evasion skill entropy
- Victim persona entropy
- Geography entropy
- Attack stage entropy

---

## 11. Blue Team — Detection

### Detection Workflow

```
detect(run_id)
    │
    ├─→ Load transactions, features, labels from store
    │
    ├─→ Split (temporal + grouped)
    │     ├─ Train: first 60% of timeline
    │     ├─ Validation: next 20% (for threshold calibration + early stopping)
    │     └─ Test: last 20% (held-out, never seen during training)
    │     All events of one attack_id land in the same split
    │
    ├─→ Train GBDT on train split
    │     eval_set = validation split (for early stopping)
    │
    ├─→ Score test split
    │     ├─ predict_proba() → fraud probability per transaction
    │     ├─ Choose threshold at target FPR (1%) on validation
    │     └─ Apply threshold to test predictions
    │
    └─→ Compute metrics on test split
          ├─ Overall: recall, precision, F1, ROC-AUC, PR-AUC, FPR
          ├─ By attack family
          ├─ By evasion skill
          ├─ Operating curve (recall at various FPR budgets)
          ├─ Risk distribution (LOW/MEDIUM/HIGH/CRITICAL)
          ├─ Customer friction (legit challenged vs fraud stopped)
          └─ Top features (cover-weighted importance)
```

### Metrics

| Metric | Description | How it's used |
|---|---|---|
| Recall | TP / (TP + FN) — share of fraud caught | Primary metric |
| Precision | TP / (TP + FP) — share of alerts that are fraud | Secondary |
| F1 | Harmonic mean of precision and recall | Summary |
| ROC-AUC | Area under ROC curve | Threshold-independent quality |
| PR-AUC | Area under precision-recall curve | Better than ROC for imbalanced data |
| FPR | FP / (FP + TN) — share of legit flagged | Business constraint |
| Alerts/1k | FP per 1,000 legitimate transactions | Analyst workload proxy |
| Scoring latency | Microseconds per transaction | Operational cost |

### Recall by Difficulty (typical)

| Difficulty | Recall | Notes |
|---|---|---|
| EASY | ~100% | Obvious anomalies, detectors catch everything |
| MEDIUM | ~50% | Some evasion, detectors partially effective |
| HARD | ~17% | Mimics legitimate behaviour, detectors mostly fail |
| ADVERSARIAL | ~0% | Optimised against the detector |

---

## 12. Risk Decision Engine

### `RiskEngine`

Converts model probability to a risk score, band, and action.

```python
class RiskEngine:
    def __init__(self, bands: List[RiskBand], target_fpr: float = 0.01):
        ...
    
    def decide(self, fraud_probability: float) -> RiskDecision:
        ...
    
    def decide_batch(self, probabilities: np.ndarray) -> List[RiskDecision]:
        ...
```

### `RiskDecision`

```python
@dataclass
class RiskDecision:
    fraud_probability: float   # Raw model output [0, 1]
    risk_score: float          # Mapped to 0–100 scale
    risk_band: str             # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    action: str                # "ALLOW", "MONITOR", "STEP_UP_AUTH", "HOLD_REVIEW"
```

### Mapping

```
fraud_probability → risk_score (monotonic mapping)
risk_score → risk_band (thresholds: 30, 60, 80)
risk_band → action (ALLOW, MONITOR, STEP_UP_AUTH, HOLD_REVIEW)
```

### Typical Risk Distribution (test split, 1% FPR budget)

| Band | Action | Count | Fraud | Legit | % of All Fraud |
|---|---|---|---|---|---|
| LOW | ALLOW | ~6,000 | ~26 | ~5,999 | ~33% |
| MEDIUM | MONITOR | ~80 | ~5 | ~74 | ~6% |
| HIGH | STEP_UP_AUTH | ~72 | ~16 | ~56 | ~21% |
| CRITICAL | HOLD_REVIEW | ~32 | ~31 | ~1 | ~40% |

---

## 13. Explainability (TreeSHAP)

### Algorithm

Implements the path-dependent TreeSHAP algorithm (Lundberg, Erion & Lee, 2020) from scratch.

#### `shap_values(model, X, check=True, tol=1e-4)`

```python
def shap_values(model: BaseModel, X: np.ndarray,
                check: bool = True, tol: float = 1e-4
                ) -> Tuple[np.ndarray, float]:
    """
    Returns:
        phi: np.ndarray of shape (n_rows, n_features) — SHAP values
        base_value: float — expected model output E[f(x)]
    
    For GBDT:
        base_value + phi[i].sum() == model.decision_function(X)[i]
    
    For RF:
        base_value + phi[i].sum() == model.predict_proba(X)[i]
    """
```

#### `_tree_shap_single(tree, xb, phi)`

Accumulates SHAP values for one row. Implements:
- Extend: traverse tree, tracking path-dependent fractional weights
- Unwind: when backtracking, distribute leaf contribution using unwound_sum
- Maintains `d_feat`, `z_frac`, `o_frac`, `weight` arrays for path tracking

#### `brute_force_shap(tree, xb, n_features)`

Reference implementation: enumerates all 2^M subsets. Limited to M ≤ 14 distinct split features. Used only for test validation.

### Verification

- Max error vs brute-force: ~3.6e-08 over 60 comparisons
- Local accuracy (base + Σφ == model output): max error ~1.7e-07

### Narrative Generation

The `POST /api/score` endpoint produces a human-readable narrative:

```
LOW risk (1.1/100) -> ALLOW. Model probability 0.001.
Principal drivers: Age of device on this account = 18.97; High-risk location = 1.
```

---

## 14. Gap Analysis

### 10 Evasion Hypotheses

Each hypothesis tests whether a specific evasion trait is over-represented among missed attacks.

| # | Key | Label | Exploit Knob | Detection Logic |
|---|---|---|---|---|
| 1 | `LOW_VALUE` | Low-value amounts | `amount_mult` | Amount stays within victim's normal range |
| 2 | `SLOW_PACING` | Slow / patient pacing | `gap` | Events spaced far apart |
| 3 | `FAMILIAR_DEVICE` | Familiar device | `p_new_device` | Device already established on account |
| 4 | `FAMILIAR_GEOGRAPHY` | Familiar geography | `p_new_city` | Home city, no geo anomaly |
| 5 | `EXISTING_PAYEE` | Existing beneficiary | `p_reuse_existing_payee` | Payee already on file |
| 6 | `MERCHANT_MIMICRY` | Merchant mimicry | `merchant_reuse` | Cash-out through familiar merchants |
| 7 | `NO_CREDENTIAL_TRACE` | No credential trace | `p_credential_change` | No password/profile change |
| 8 | `LOW_VELOCITY_FOOTPRINT` | Low velocity footprint | `n_drain` | Normal daily rhythm |
| 9 | `THIN_BUT_CLEAN_IDENTITY` | Aged synthetic identity | `identity_quality` | Old enough to look established |
| 10 | `SEQUENCE_ONLY` | Visible only as a sequence | `spread_days` | Individually unremarkable events |

### Attribution

Attribution is derived from **excess prevalence**: how much more common a trait is among misses than among catches.

```
attribution = (share_of_missed - share_of_detected) × prevalence_among_misses
```

A trait present in 90% of misses but also 90% of catches explains nothing (attribution ≈ 0).

### GapReport Output

```python
@dataclass
class GapReport:
    n_attacks: int
    n_detected: int
    n_missed: int
    recall: float
    threshold: float
    causes: List[Dict]          # Each with: key, label, share_of_missed,
                                # share_of_detected, lift, attribution, remediation
    by_attack_type: List[Dict]  # Group-level recall
    by_difficulty: List[Dict]
    by_stage: List[Dict]
    weakest_segments: List[Dict] # Attack family × difficulty segments
    examples: List[Dict]        # Worked examples of confident misses
    calibration: Dict[str, float]
```

### Typical Attribution (test split)

| Evasion Trait | % of Misses | % of Catches | Lift | Attribution |
|---|---|---|---|---|
| Merchant mimicry | 87% | 45% | 1.95× | 22% |
| Low-value amounts | 42% | 9% | 4.93× | 18% |
| Familiar geography | 100% | 77% | 1.31× | 13% |
| Aged synthetic identity | 65% | 43% | 1.52× | 12% |
| Visible only as a sequence | 23% | 2% | 10.61× | 11% |

---

## 15. Adaptive Attack/Defence Loop

### Workflow

```
adversarial_loop(run_id, n_adversarial, use_search, search_rounds, intensity)
    │
    ├─1→ diagnose()
    │      Identify weakest segments and evasion traits via gap analysis
    │
    ├─2→ adapt_knobs()
    │      For each identified weakness, adjust attack parameters:
    │      - merchant_reuse: increase p_reuse_existing_payee
    │      - amount_mult: compress drain to victim's normal range
    │      - p_new_city: stay in victim's home city
    │      - p_new_device: use established devices
    │      etc.
    │
    ├─3→ Generate adversarial attacks (two batches)
    │      ├─ adv_train: used for retraining
    │      └─ adv_eval: held out, used for final evaluation
    │
    ├─4→ (Optional) evasion search
    │      Black-box search: candidates scored by deployed detector,
    │      only most evasive kept. Like an attacker probing a live endpoint.
    │
    ├─5→ Retrain on original + adv_train
    │      Hardened model sees both normal and adversarial attacks
    │
    └─6→ Evaluate on adv_eval
           Measures improvement at matched FPR budget
```

### Adaptation Plan Moves

Each move is an auditable knob change:

```python
{
    "cause_label": "Merchant mimicry",
    "knob": "merchant_reuse",
    "lift": 1.95,
    "share_of_missed": 0.87,
    "rationale": "Acceptance-side novelty is being caught, so cash out
                  through merchants the victim already transacts with."
}
```

### Regression Check

The hardened model is also evaluated on the **original attack distribution** to ensure hardening against new attacks doesn't degrade performance on existing ones.

### Key Constraint

The false-positive budget is held constant on both sides. If the hardened model catches more fraud but also flags more legitimate traffic, that's not a real improvement.

---

## 16. REST API

All endpoints served by `sovereignguard/api/server.py` using Python's stdlib `http.server`.

### Base URL

```
http://localhost:8000
```

### Endpoints

#### GET /api/health
Returns backend status and loaded state.

**Response:**
```json
{
    "status": "ok",
    "service": "sovereignguard",
    "version": "0.1.0",
    "time": 1724000000.0,
    "ml_backend": "numpy",
    "optional_backends": {"xgboost": false, "lightgbm": false, "sklearn": false, "shap": false},
    "loaded_worlds": ["run_abc123"],
    "loaded_detectors": ["run_abc123:default"],
    "default_run": "run_abc123",
    "frontend_present": true
}
```

#### GET /api/config
Returns all configuration constants for the frontend.

**Response:**
```json
{
    "scales": {"nano": {...}, "tiny": {...}, "demo": {...}},
    "default_scale": "demo",
    "attack_types": ["ACCOUNT_TAKEOVER", ...],
    "difficulties": ["EASY", "MEDIUM", "HARD", "ADVERSARIAL"],
    "difficulty_descriptions": {"EASY": "...", ...},
    "risk_bands": [{"lower": 0, "upper": 30, "name": "LOW", "action": "ALLOW"}, ...],
    "target_fpr_budget": 0.01,
    "n_features": 83,
    "feature_labels": {"amount": "Transaction amount", ...},
    "seed": 20260823
}
```

#### GET /api/taxonomy
Returns the full attack taxonomy (loaded from `data/attack_taxonomy.json`).

**Response:**
```json
{
    "version": "1.0",
    "description": "...",
    "genai_amplification_note": "...",
    "difficulty_levels": {"EASY": "...", "MEDIUM": "...", "HARD": "...", "ADVERSARIAL": "..."},
    "cross_cutting_patterns": [...],
    "attacks": [
        {
            "attack_type": "ACCOUNT_TAKEOVER",
            "attack_name": "Account Takeover",
            "family": "...",
            "severity": "HIGH",
            "n_stages": 6,
            "stages": ["RECON_LOGIN", ...],
            "target": "...",
            "genai_role": "...",
            "expected_signals": [...],
            "behavioural_changes": [...],
            "mitigations": [...],
            "hard_variant_note": "...",
            "payment_surfaces": [...],
            "base_rate_prior": 0.08
        },
        ...
    ]
}
```

#### GET /api/taxonomy/{attack_type}
Returns a single attack family's taxonomy entry.

#### GET /api/runs
Lists all simulation runs (in-memory and persisted).

**Response:**
```json
{
    "runs": ["run_abc123", ...],
    "default_run": "run_abc123",
    "in_memory": ["run_abc123"]
}
```

#### GET /api/runs/{run_id}
Returns a specific run's record including summary.

#### POST /api/simulate
Starts a full simulation (build world + train). Returns a job ID for polling.

**Request:**
```json
{
    "scale": "tiny",               // optional, default "tiny"
    "seed": 20260823,              // optional
    "target_prevalence": 0.01,     // optional
    "model_kind": "gbdt",          // optional, "gbdt" or "forest"
    "attack_types": null,          // optional, null = all 7
    "difficulty_mix": null,        // optional
    "train": true,                 // optional
    "persist": true                // optional
}
```

**Response (202):**
```json
{"job_id": "job_xyz", "status": "running"}
```

**Job progress (poll GET /api/jobs/{job_id}):**
```json
{
    "job_id": "job_xyz",
    "kind": "simulate",
    "status": "running",
    "progress": [
        {"t": 1724000001.0, "message": "Building population..."},
        {"t": 1724000002.0, "message": "Generating transactions..."},
        ...
    ],
    "result": null
}
```

**Job completion:**
```json
{
    "status": "complete",
    "result": {
        "run_id": "run_abc123",
        "summary": {
            "n_transactions": 31000,
            "n_fraud_events": 310,
            "fraud_prevalence": 0.01,
            "n_attack_scenarios": 120,
            "attack_types": ["ACCOUNT_TAKEOVER", ...],
            "window_days": 30
        }
    }
}
```

#### POST /api/detect
Scores all test transactions with the trained detector.

**Request:**
```json
{
    "run_id": "run_abc123",         // required
    "detector_key": null            // optional
}
```

**Response (200):**
```json
{
    "overall": {
        "recall": 0.6026,
        "precision": 0.4519,
        "f1": 0.5165,
        "roc_auc": 0.9530,
        "pr_auc": 0.6089,
        "fpr": 0.00930,
        "tp": 47, "fn": 31, "fp": 57, "tn": 6151,
        "alerts_per_1k_legit": 9.30,
        "latency_us_per_txn": 9.6,
        "n_positive": 78,
        "value_detected_share": 0.603
    },
    "by_attack_type": [
        {"group": "ACCOUNT_TAKEOVER", "n": 7, "recall": 0.286},
        {"group": "TRANSACTION_MANIPULATION", "n": 28, "recall": 0.464},
        ...
    ],
    "by_difficulty": [
        {"group": "EASY", "n": 31, "recall": 1.0},
        {"group": "MEDIUM", "n": 23, "recall": 0.522},
        {"group": "HARD", "n": 24, "recall": 0.167}
    ],
    "operating_curve": [
        {"fpr_budget": 0.001, "realised_fpr": 0.00098, "recall": 0.308, "precision": 0.583, "alerts_per_1k_legit": 9.8},
        ...
    ],
    "risk_distribution": [
        {"band": "LOW", "action": "ALLOW", "count": 6025, "fraud": 26, "legit": 5999, "share_of_all_fraud": 0.333},
        ...
    ],
    "friction": {
        "legit_challenged_share": 0.0093,
        "fraud_stopped_share": 0.603,
        "fraud_allowed_share": 0.397,
        "legit_allowed_share": 0.9907
    },
    "threshold": 0.037046,
    "target_fpr": 0.01,
    "top_features": [
        {"feature": "customer_merchant_txn_count", "label": "Prior transactions with this merchant", "importance": 0.1076},
        ...
    ],
    "n_scored": 6208
}
```

#### POST /api/score
Explains a single transaction decision via TreeSHAP.

**Request:**
```json
{
    "run_id": "run_abc123",         // required
    "detector_key": null,           // optional
    "transaction_id": null,         // optional — explain this specific txn
    "worst_missed": true,           // optional — explain the worst miss
    "index": 0,                     // optional — explain by row index
    "top_k": 6                      // optional — number of SHAP features
}
```

**Response (200):**
```json
{
    "transaction": {
        "transaction_id": "TXN_ATK_TRAH000028_07",
        "customer_id": "C_...",
        "merchant_id": "M_...",
        "amount": 7267.78,
        "payment_method": "UPI",
        "channel": "APP",
        "transaction_type": "TRANSFER",
        "city": "Mumbai",
        "fraud_label": 1,
        "attack_type": "TRANSACTION_MANIPULATION",
        "attack_stage": "STRUCTURE",
        "difficulty": "HARD"
    },
    "decision": {
        "fraud_probability": 0.001,
        "risk_score": 1.1,
        "risk_band": "LOW",
        "action": "ALLOW"
    },
    "explanation": {
        "base_value": -1.8326,
        "reasons": [
            {"label": "Age of device on this account", "feature": "device_age_days", "value": 18.968, "contribution": 0.19620},
            {"label": "High-risk location", "feature": "is_high_risk_location", "value": 1.0, "contribution": 0.15770}
        ],
        "protective_factors": [
            {"label": "Prior transactions with this merchant", "feature": "customer_merchant_txn_count", "value": 12.0, "contribution": -1.44410},
            {"label": "Age of the identity's digital footprint", "feature": "digital_footprint_days", "value": 5030.0, "contribution": -0.85189}
        ]
    },
    "narrative": "LOW risk (1.1/100) -> ALLOW. Model probability 0.001. Principal drivers: ...",
    "is_correct": false
}
```

#### POST /api/redteam/generate
Generates new attack scenarios.

**Request:**
```json
{
    "run_id": "run_abc123",         // required
    "n_scenarios": 200,             // optional, 1–20000
    "attack_types": null,           // optional, null = all
    "difficulty": "HARD",           // optional
    "difficulty_mix": null          // optional
}
```

**Response (200):**
```json
{
    "n_scenarios": 200,
    "n_events": 1947,
    "diversity": {
        "entropy_attack_type": 0.977,
        "entropy_difficulty": 0.973,
        "entropy_persona": 0.930,
        "entropy_city": 0.920,
        "entropy_stage": 0.847,
        "distinct_devices": 412,
        "distinct_cities": 19,
        "distinct_merchants": 380,
        "distinct_stages": 27,
        "distinct_victims": 180,
        "distinct_victim_personas": 7,
        "events_per_scenario_mean": 9.7,
        "amount_span_log10": 3.7,
        "amount_p05": 110,
        "amount_p95": 40906
    },
    "scenarios_sample": [...],
    "events_sample": [...],
    "by_type": {"ACCOUNT_TAKEOVER": 30, ...},
    "by_difficulty": {"HARD": 200}
}
```

#### POST /api/gap
Runs gap analysis on the test split.

**Request:**
```json
{
    "run_id": "run_abc123",         // required
    "detector_key": null,           // optional
    "model_run_id": "adhoc",        // optional
    "on": "test"                    // optional, "test" or "train"
}
```

**Response (200):** Full `GapReport` dict (see section 14).

#### POST /api/loop
Starts the adaptive attack/defence loop.

**Request:**
```json
{
    "run_id": "run_abc123",         // required
    "detector_key": null,           // optional
    "n_adversarial": 200,           // optional
    "use_search": true,             // optional
    "search_rounds": 2,             // optional
    "intensity": 0.85,              // optional
    "model_kind": "gbdt"            // optional
}
```

**Response (202):** `{"job_id": "job_xyz", "status": "running"}`

**Job completion result:**
```json
{
    "before": {"recall": 0.2336, "precision": 0.7811, "f1": 0.3597, ...},
    "after": {"recall": 0.1986, "precision": 0.7652, "f1": 0.3154, ...},
    "delta": {"recall_delta": -0.0350, "f1_delta": -0.0443, ...},
    "adaptation_plan": {
        "moves": [
            {
                "cause_label": "Merchant mimicry",
                "knob": "merchant_reuse",
                "lift": 1.95,
                "share_of_missed": 0.87,
                "rationale": "..."
            },
            ...
        ],
        "target_segments": [...]
    },
    "baseline_on_baseline": {...},
    "hardened_on_baseline": {...},
    "search_history": [...],
    "meta": {
        "methodology": "...",
        "adv_train_scenarios": 100,
        "adv_eval_scenarios": 100,
        "eval_population": {"n": 6778, "n_fraud": 886},
        "target_fpr": 0.01,
        "threshold_before": 0.037,
        "threshold_after": 0.039,
        "model_kind": "gbdt",
        "used_search": true,
        "elapsed_seconds": 45.2
    }
}
```

#### GET /api/loop/latest
Returns the most recent loop result (if any).

#### GET /api/jobs/{job_id}
Returns job status and progress.

#### GET /api/models
Lists saved model runs.

#### GET /api/experiments
Lists available experiment results.

#### GET /api/experiments/{id}
Returns a specific experiment result.

---

## 17. Frontend Dashboard

### Pages (7 views)

| Page | Path | Description |
|---|---|---|
| Overview | `overview` | Situation room: KPIs, risk distribution, operating curve |
| Intelligence | `intel` | Attack taxonomy browser, 7 families, difficulty levels |
| Red Team | `redteam` | Attack campaign configurator and generator |
| Blue Team | `blueteam` | Detection metrics, recall by difficulty/family, feature importance |
| Explain | `explain` | Per-transaction TreeSHAP waterfall and reason codes |
| Gap Analysis | `gap` | 10-evasion-hypothesis report, attribution, weakest segments |
| Adaptive Loop | `loop` | Hero screen: before/after comparison, adaptation moves |

### Shared State

All views share state lifted to `pages/index.jsx`:

```javascript
{
    run: Object,         // Current simulation run
    busy: Boolean,       // Simulation in progress
    simulate: Function,  // Trigger a new simulation
    health: Object,      // Backend health status
    detect: Object,      // Detection results (cached)
    setDetect: Function,
    gap: Object,         // Gap analysis results (cached)
    setGap: Function,
    loop: Object,        // Adaptive loop results (cached)
    setLoop: Function,
    goto: Function,      // Navigate to a page
    progress: Array,     // Build progress messages
    simError: Object,    // Simulation error
}
```

### API Client (`lib/api.js`)

| Function | Description |
|---|---|
| `get(path)` | GET request, returns parsed JSON |
| `post(path, payload)` | POST request with JSON body |
| `runJob(path, payload, onProgress, intervalMs)` | Async job: POST → poll → return result |
| `pct(v, digits)` | Format as percentage: `0.1234` → `"12.3%"` |
| `num(v, digits)` | Format number: `0.1234` → `"0.1234"` |
| `int(v)` | Format integer with commas: `12345` → `"12,345"` |
| `money(v)` | Format as rupees: `1234` → `"₹1,234"` |
| `signed(v, digits)` | Format with sign: `0.123` → `"+0.123"` |
| `severityClass(s)` | Map severity to CSS class |
| `bandClass(b)` | Map risk band to CSS class |
| `recallColour(r)` | Map recall to background colour |
| `shortAttack(t)` | Map attack type to display name |

### Chart Components (`components/Charts.jsx`)

| Component | Description | Props |
|---|---|---|
| `BarChart` | Horizontal bar chart | `data`, `height`, `format`, `colour`, `max`, `emptyLabel` |
| `StackedBar` | Stacked horizontal bar | `segments`, `height`, `emptyLabel` |
| `LineChart` | Multi-series line chart | `series`, `xLabel`, `yLabel`, `height`, `xFormat`, `yFormat` |
| `Gauge` | Risk score gauge (semi-circle) | `value`, `max`, `label`, `band` |
| `Waterfall` | SHAP waterfall (bidirectional) | `reasons`, `protective`, `height`, `emptyLabel` |
| `DeltaBar` | Before/after comparison | `before`, `after`, `label`, `format` |
| `StagePipeline` | Attack stage pipeline | `stages` |
| `EntropyBar` | Diversity entropy bar | `value`, `label` |

### UI Components (`components/UI.jsx`)

| Component | Description | Props |
|---|---|---|
| `Kpi` | Key performance indicator card | `label`, `value`, `sub`, `tone`, `big` |
| `Card` | Content card with header | `title`, `subtitle`, `children`, `actions`, `tone` |
| `Table` | Data table | `columns`, `rows`, `empty`, `rowKey` |
| `Badge` | Status badge | `children`, `className` |
| `Skeleton` | Loading placeholder | `lines`, `height` |
| `ErrorNote` | Error display | `error`, `onRetry` |
| `EmptyState` | Empty state placeholder | `title`, `body`, `action` |
| `ProgressLog` | Streaming progress log | `lines`, `running`, `title` |
| `RunBanner` | Active run status bar | `run`, `onSimulate`, `busy` |
| `useHealth` | Backend health hook | Returns `{health, error}` |

### Design System (`styles/globals.css`)

- **Base:** Deep navy dark theme (`#080b12`)
- **Surfaces:** 4-layer hierarchy (`--surface-1` through `--surface-4`)
- **Typography:** System font stack, tabular-nums for numeric values
- **Accent colours:** Blue (`--accent`), Green (`--green`), Red (`--red`), Amber (`--amber`), Violet (`--violet`)
- **Components:** Cards, KPIs, tables, badges, buttons (ghost/primary/red/hero)
- **Charts:** Hand-drawn SVG with grid lines, tick marks, legends
- **Responsive:** 3 breakpoints (1400px, 1180px, 860px)

---

## 18. CLI Reference

### Entry Point

```bash
python sg.py <command> [options]
```

### Commands

| Command | Description | Key Options |
|---|---|---|
| `demo` | Full loop in one command | `--scale`, `--seed` |
| `build` | Build synthetic world | `--scale`, `--save`, `--seed` |
| `train` | Train a detector | `--model gbdt/forest`, `--scale` |
| `redteam` | Generate attacks | `--difficulty HARD`, `-n 500` |
| `gap` | Run gap analysis | (uses last run) |
| `loop` | Run adaptive loop | `-n 400`, `--rounds 2` |
| `experiments` | Run all 6 experiments | (no options) |
| `serve` | Start REST API + dashboard | `--port 8000` |
| `taxonomy` | Print attack taxonomy | (no options) |

### Examples

```bash
# Quick test at nano scale
python sg.py demo --scale nano

# Full simulation at demo scale
python sg.py build --scale demo --save
python sg.py train --model gbdt
python sg.py redteam --difficulty HARD -n 500
python sg.py gap

# Adaptive loop
python sg.py loop -n 400 --rounds 2

# Start the dashboard
python sg.py serve  # API on :8000, dashboard on :3000
```

---

## 19. Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim-bookworm
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
HEALTHCHECK CMD curl -f http://localhost:8000/api/health || exit 1
ENTRYPOINT ["python", "sg.py"]
```

### docker-compose.yml (5 services)

| Service | Command | Port | Description |
|---|---|---|---|
| `backend` | `serve` | 8000 | REST API only |
| `dashboard` | `serve` (with frontend) | 3000 + 8000 | Full stack |
| `demo` | `demo` | — | One-shot full loop |
| `experiments` | `experiments` | — | One-shot experiment suite |
| `postgres` | (optional profile) | 5432 | PostgreSQL backend |

### Usage

```bash
# API only
docker compose up backend

# Full stack
docker compose up

# One-shot demo
docker compose run --rm demo

# One-shot experiments
docker compose run --rm experiments
```

### Named Volume

SQLite database uses a named volume to avoid POSIX locking issues on bind mounts:

```yaml
volumes:
  sgstate:
```

---

## 20. Verification & Testing

### Test Suite (`tests/run_tests.py`)

82 tests, no pytest required. Custom runner with fixtures from `conftest.py`.

| Module | Tests | What it covers |
|---|---|---|
| `test_schema.py` | 3 | Feature/label contract, FEATURE_LABELS completeness |
| `test_features.py` | 8 | Causality under truncation, velocity windows, hand-computed arithmetic |
| `test_generators.py` | 6 | Population generation, attack generation, diversity |
| `test_detection_api.py` | 5 | Training, scoring, API 400/404 handling |
| `test_leakage_audit.py` | 2 | Single-feature AUC oracle (all 83 < 0.99) |
| `test_metrics_risk.py` | 6 | Metric known-answers, risk engine |
| `test_ml.py` | 8 | TreeSHAP brute-force verification, GBDT correctness |

### End-to-End Verification (`verify.py`)

14 staged assertions, each checking concrete properties:

| Stage | Name | What it checks |
|---|---|---|
| 1 | `env` | Python version, numpy/pandas import, module imports |
| 2 | `tests` | Full test suite passes |
| 3 | `world` | Synthetic data generation, realism checks |
| 4 | `redteam` | Attack generation, diversity, difficulty gradient |
| 5 | `blueteam` | Detection metrics, recall by difficulty/family |
| 6 | `explain` | TreeSHAP vs brute-force, local accuracy |
| 7 | `risk` | Risk score monotonicity, band routing |
| 8 | `gap` | Gap analysis, evasion trait attribution |
| 9 | `loop` | Adaptive loop, matched FPR, regression check |
| 10 | `audit` | Leakage audit, synthetic-identity separability |
| 11 | `api` | REST API endpoints, status codes |
| 12 | `store` | SQLite persistence, model save/load |
| 13 | `cli` | CLI commands |
| 14 | `frontend` | Static import/export resolution |

### Usage

```bash
python verify.py              # Full run (~4 min at demo scale)
python verify.py --quick      # Nano scale (~90s)
python verify.py --full       # Demo scale (~15 min)
python verify.py --stage gap  # Single stage
python verify.py --list       # Show stage names
```

### Critical Assertions

1. **No label leakage:** Single-feature AUC for all 83 features must be < 0.99
2. **No campaign leakage:** All events of one `attack_id` in the same split
3. **Causality:** Features computed with bit-identical output at 25%/50%/75% truncation
4. **Honest rates non-zero:** `LEGIT_EVENT_RATES` values prevent perfect oracles
5. **Recall gain real:** Improvement measured at matched FPR budget

---

## 21. Experiments

6 experiments in `experiments/run_all.py`, results in `experiments/results/`.

### Experiment 1: Baseline
- 4 runs: 2 prevalences (1%, 3%) × 2 models (GBDT, RF)
- Bootstrap 95% confidence intervals
- Key finding: GBDT achieves 60% recall at 1% FPR, RF achieves 55%

### Experiment 2: Attack Diversity
- Sweep 1/3/5/7 attack families
- Key finding: diversity improves recall of the overall population but HARD recall drops

### Experiment 3: Unseen Attacks
- 3 holdout groups: hold out one attack type, one difficulty, one family
- Key finding: recall retention 40–64% — detectors generalise partially to unseen attacks

### Experiment 4: Adversarial Pressure
- Compare ordinary vs adversarial attacks
- Key finding: ordinary 59% recall drops to 26% under adversarial pressure (−33.4 pts)

### Experiment 5: Adaptive Training
- Before/after adaptive loop
- Key finding: 22% → 35.5% recall improvement (+13.5 pts), but baseline recall falls 11.1 pts

### Experiment 6: False Positives
- FPR sweep from 0.1% to 5%
- Key finding: persona-level fairness — 3.2× disparity in FPR across personas

---

## 22. Critical Design Decisions

### 1. No External ML Libraries
All GBDT, Random Forest, and TreeSHAP are implemented from scratch in numpy. This ensures:
- Zero dependency risk (no XGBoost version conflicts)
- Full control over the training pipeline
- Verifiable correctness (brute-force TreeSHAP verification)

### 2. Causality is Structural
Features for row *t* use only data before *t*. History is appended only after a row's features are emitted. This is not a convention — it's enforced by the streaming architecture.

### 3. No Accuracy Reporting
At ~1% fraud prevalence, a model that approves everything scores 99% accuracy and is worthless. All metrics are precision/recall quantities at a fixed false-positive budget.

### 4. Two Independent Adversarial Batches
The adversarial loop uses `adv_train` (for retraining) and `adv_eval` (for evaluation). They are never the same, preventing evaluation overfitting.

### 5. Temporal + Grouped Splits
Splits respect both time (train before validation before test) and campaign identity (all events of one `attack_id` in the same split). Random shuffling would break this.

### 6. Honest Customers Do Suspicious Things
Rates in `LEGIT_EVENT_RATES` are non-zero. New devices, new payees, travel — all happen legitimately. This prevents trivial feature oracles.

### 7. Three Label Leaks Found and Fixed
The leakage audit (`test_leakage_audit.py`) found three features that leaked labels:
1. `device_reputation` — was computed using future fraud labels
2. `device_registration_distribution` — leaked device registration timing
3. `digital_footprint_days` — was derived from attack injection timestamps

### 8. Scale Profiles Matter
- `nano` (300 customers, 21 days): fast iteration, wide confidence intervals
- `demo` (400 customers, 30 days): load-bearing results
- `large` (10,000 customers, 60 days): production-scale testing

### 9. Frontend is Statically Verified
The verification harness checks that all imports/exports resolve and that `globals.css` is only imported from `_app.jsx`. No TypeScript, no linting — just structural checks.

### 10. REST API Uses stdlib
The API uses Python's `http.server` with JSON contracts identical to what FastAPI would produce. This keeps the dependency surface minimal while maintaining a clean API contract.
