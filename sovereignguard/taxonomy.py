"""Loader / accessor for the attack knowledge base (Pillar 1: Identify)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from . import config as C

TAXONOMY_PATH = C.DATA_DIR / "attack_taxonomy.json"


@lru_cache(maxsize=1)
def load_taxonomy() -> dict:
    with open(TAXONOMY_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def attack_entries() -> List[dict]:
    return load_taxonomy()["attacks"]


@lru_cache(maxsize=1)
def by_type() -> Dict[str, dict]:
    return {a["attack_type"]: a for a in attack_entries()}


def get(attack_type: str) -> dict:
    try:
        return by_type()[attack_type]
    except KeyError:
        raise KeyError(f"Unknown attack_type {attack_type!r}. "
                       f"Known: {sorted(by_type())}") from None


def stages(attack_type: str) -> List[str]:
    return list(get(attack_type)["stages"])


def severity(attack_type: str) -> str:
    return get(attack_type)["severity"]


def base_rate_prior(attack_type: str) -> float:
    return float(get(attack_type)["base_rate_prior"])


def type_mix() -> Dict[str, float]:
    """Normalised prior over attack types, used when sampling a mixed campaign."""
    raw = {a["attack_type"]: float(a["base_rate_prior"]) for a in attack_entries()}
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}


def difficulty_levels() -> Dict[str, str]:
    return dict(load_taxonomy()["difficulty_levels"])


def expected_signals(attack_type: str) -> List[str]:
    return list(get(attack_type)["expected_signals"])


def summary_table() -> List[dict]:
    """Compact view for the Attack Intelligence dashboard page."""
    out = []
    for a in attack_entries():
        out.append({
            "attack_type": a["attack_type"],
            "attack_name": a["attack_name"],
            "family": a["family"],
            "severity": a["severity"],
            "base_rate_prior": a["base_rate_prior"],
            "target": a["target"],
            "payment_surfaces": a["payment_surfaces"],
            "genai_role": a["genai_role"],
            "n_stages": len(a["stages"]),
            "stages": a["stages"],
            "behavioural_changes": a["behavioural_changes"],
            "expected_signals": a["expected_signals"],
            "hard_variant_note": a["hard_variant_note"],
            "mitigations": a["mitigations"],
        })
    return out


def validate() -> None:
    """Fail loudly if the taxonomy and config disagree."""
    known = set(by_type())
    cfg = set(C.ATTACK_TYPES)
    if known != cfg:
        raise RuntimeError(
            f"Taxonomy/config mismatch. Only in taxonomy: {known - cfg}. "
            f"Only in config: {cfg - known}")
    from .schema import FEATURE_COLUMNS
    feats = set(FEATURE_COLUMNS)
    for a in attack_entries():
        bad = [s for s in a["expected_signals"] if s not in feats]
        if bad:
            raise RuntimeError(f"{a['attack_type']} references unknown features: {bad}")
