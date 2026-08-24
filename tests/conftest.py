"""
Shared fixtures.

Memoised plain functions, exposed as pytest fixtures when pytest is available.
The suite must run BOTH under pytest and via `python tests/run_tests.py`, because
pytest is not guaranteed to be installed.

Everything is deliberately tiny so the whole suite finishes in a couple of
minutes; correctness properties do not need scale to be violated.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SEED = 20260823
_cache: dict = {}


def tiny_population():
    if "pop" not in _cache:
        from sovereignguard.generators.population import build_population
        _cache["pop"] = build_population(80, 60, SEED)
    return _cache["pop"]


def tiny_legit_tx():
    if "legit" not in _cache:
        from sovereignguard.generators.transactions import generate_legitimate_transactions
        cu, me, dv = tiny_population()
        _cache["legit"] = generate_legitimate_transactions(cu, me, dv, 12, SEED)
    return _cache["legit"]


def tiny_features():
    if "feats" not in _cache:
        from sovereignguard.features import build_features
        cu, me, dv = tiny_population()
        _cache["feats"] = build_features(tiny_legit_tx(), cu, me, dv)
    return _cache["feats"]


def tiny_world():
    """A world with fraud injected, big enough to train on."""
    if "world" not in _cache:
        from sovereignguard.pipeline import build_world
        _cache["world"] = build_world("nano", SEED, target_prevalence=0.02, quiet=True)
    return _cache["world"]


def tiny_detector():
    if "det" not in _cache:
        from sovereignguard.pipeline import train_baseline
        w = tiny_world()
        det, split = train_baseline(w, "gbdt", quiet=True)
        _cache["det"] = (det, split)
    return _cache["det"]


FIXTURES = {
    "tiny_population": tiny_population,
    "tiny_legit_tx": tiny_legit_tx,
    "tiny_features": tiny_features,
    "tiny_world": tiny_world,
    "tiny_detector": tiny_detector,
}

try:  # pragma: no cover - only when pytest is installed
    import pytest

    def _mk(fn):
        @pytest.fixture(scope="session")
        def _f():
            return fn()
        return _f

    for _name, _fn in FIXTURES.items():
        globals()[_name] = _mk(_fn)
except ImportError:
    pass
