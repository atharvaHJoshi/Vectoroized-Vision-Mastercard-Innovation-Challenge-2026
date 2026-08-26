# AGENTS.md

## What this is

SovereignGuard — a synthetic payment-fraud testing lab. Python ML core (numpy/pandas only) + Next.js dashboard. No external ML libraries required; everything (GBDT, RF, TreeSHAP) is built from scratch in numpy.

## Commands

### Testing
```bash
python tests/run_tests.py           # 82 tests, ~19s, no pytest needed
python tests/run_tests.py -v        # full tracebacks on failure
python tests/run_tests.py test_features   # run one module only
```

### Verification (end-to-end, asserts correctness)
```bash
python verify.py                    # full, ~4 minutes
python verify.py --quick            # nano scale, ~90s
python verify.py --full             # demo scale, ~15 min
python verify.py --stage tests      # single stage only
python verify.py --list             # show stage names
```

### CLI entry points
```bash
python sg.py demo                   # full loop, one command
python sg.py build --scale demo --save
python sg.py train --model gbdt
python sg.py redteam --difficulty HARD -n 500
python sg.py gap
python sg.py loop -n 400
python sg.py experiments
python sg.py serve                  # REST API + dashboard on :8000
python sg.py taxonomy
```

### Frontend
```bash
cd frontend && npm install && npm run dev   # dashboard on :3000
```

### Docker
```bash
docker compose up backend           # API on :8000
docker compose up                   # backend + dashboard
docker compose run --rm demo        # one-shot full loop
docker compose run --rm experiments # one-shot experiment suite
```

## Architecture

- **`sg.py`** — CLI entry point, dispatches to `sovereignguard.pipeline`
- **`sovereignguard/pipeline.py`** — `build_world()`, `train_baseline()`, `diagnose()`, `adversarial_loop()`
- **`sovereignguard/config.py`** — all constants: personas, categories, cities, risk bands, scales, attack types
- **`sovereignguard/schema.py`** — feature/label contracts, leakage guard. FEATURE_COLUMNS and LABEL_COLUMNS must never overlap.
- **`sovereignguard/features.py`** — 83 causal features, strict causality: features for row *t* use only data before *t*
- **`sovereignguard/detection.py`** — splits, training, scoring, explanation, `optional_backends()`
- **`sovereignguard/ml/`** — histogram GBDT (`tree.py`), random forest + GBDT wrapper (`models.py`), TreeSHAP (`treeshap.py`)
- **`sovereignguard/generators/`** — synthetic population, transactions, attacks, adversarial generation
- **`sovereignguard/evaluation/`** — metrics, gap analysis (10 evasion hypotheses)
- **`sovereignguard/api/server.py`** — stdlib `http.server` REST API (no FastAPI)
- **`data/attack_taxonomy.json`** — 7-family attack knowledge base
- **`frontend/`** — Next.js 14, plain JS/JSX (not TypeScript), 7 pages

## Critical gotchas

1. **No label leakage allowed.** The leakage audit (`test_leakage_audit.py`) computes single-feature AUC for all 83 features; anything > 0.99 is a leak. Three leaks were found and fixed historically — see README for details. If you add a feature, it must pass this audit.

2. **Causality is structural.** Features are computed on a transaction stream where history is appended only *after* a row's features are emitted. The test `test_causality_under_truncation` verifies bit-identical output when the stream is truncated at 25%, 50%, 75%. Do not use future data in feature computation.

3. **Campaign leakage across splits is forbidden.** All events of one `attack_id` must land in the same split. Random shuffling would break this. The verify harness checks for it.

4. **Honest customers do suspicious things.** Rates in `config.LEGIT_EVENT_RATES` — new devices, payees, travel — are non-zero by design. If any rate were 0, the corresponding flag becomes a perfect fraud oracle and all metrics are meaningless.

5. **Tests run without pytest.** `tests/run_tests.py` is the primary runner. Fixtures come from `conftest.FIXTURES` (memoised plain functions). Pytest works if installed but is not required.

6. **`verify.py` stages assert, not just run.** Each stage checks concrete properties. A green run is evidence the pipeline works, not just that it ran. Use `--stage` to run individual stages in isolation; dependencies are built on demand.

7. **Scale profiles matter.** `--scale nano` (300 customers, 21 days) for fast iteration. `--scale demo` (400 customers, 30 days) for load-bearing results. Confidence intervals are wide at nano scale.

8. **Frontend is statically checked only.** `verify.py` stage 14 resolves imports/exports but cannot run `next build` in all environments. Run `npm run build` in `frontend/` separately to verify.

## Conventions

- All ML implemented in numpy from scratch — no XGBoost, LightGBM, or sklearn dependency. `detection.optional_backends()` checks what's available for cross-validation.
- REST API uses `http.server` with JSON contracts identical to what FastAPI would produce.
- No linting, formatting, or type-checking tools are configured. No CI/CD pipeline exists.
- Experiment results are JSON artefacts in `experiments/results/` — each contains raw numbers + environment config.
- Risk bands and thresholds are prototype policy values, not production thresholds.
