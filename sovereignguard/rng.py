"""Seeded randomness helpers — every stochastic component draws from here so
that a single seed reproduces an entire pipeline run bit-for-bit."""
from __future__ import annotations

import hashlib
from typing import Dict, Iterable, List, Sequence

import numpy as np


def substream(seed: int, name: str) -> np.random.Generator:
    """Derive an independent generator for a named stage.

    Using a hash of the stage name means adding a new stage never perturbs the
    random draws of existing stages, which keeps experiments comparable.
    """
    h = hashlib.blake2b(name.encode("utf-8"), digest_size=8).digest()
    offset = int.from_bytes(h, "big") % (2**31)
    return np.random.default_rng(seed + offset)


def weighted_choice(rng: np.random.Generator, mapping: Dict[str, float], size: int | None = None):
    keys = list(mapping.keys())
    p = np.asarray([mapping[k] for k in keys], dtype=float)
    p = p / p.sum()
    return rng.choice(keys, size=size, p=p)


def choice_from(rng: np.random.Generator, items: Sequence, weights: Iterable[float] | None = None,
                size: int | None = None, replace: bool = True):
    if weights is None:
        return rng.choice(len(items), size=size, replace=replace)
    w = np.asarray(list(weights), dtype=float)
    w = w / w.sum()
    return rng.choice(len(items), size=size, replace=replace, p=w)


def lognormal(rng: np.random.Generator, mu: float, sigma: float, size: int | None = None):
    return rng.lognormal(mean=mu, sigma=sigma, size=size)


def clipped_int(value: float, lo: int, hi: int) -> int:
    return int(min(max(round(value), lo), hi))


def stable_hash_unit(*parts: object) -> float:
    """Deterministic float in [0,1) from arbitrary parts (no RNG state needed)."""
    s = "|".join(str(p) for p in parts)
    h = hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2**64


def haversine_km(lat1, lon1, lat2, lon2):
    """Vectorised great-circle distance in km."""
    lat1, lon1, lat2, lon2 = map(np.asarray, (lat1, lon1, lat2, lon2))
    r = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2.0) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2.0) ** 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def softmax_weights(values: List[float], temperature: float = 1.0) -> np.ndarray:
    v = np.asarray(values, dtype=float) / max(temperature, 1e-9)
    v = v - v.max()
    e = np.exp(v)
    return e / e.sum()
