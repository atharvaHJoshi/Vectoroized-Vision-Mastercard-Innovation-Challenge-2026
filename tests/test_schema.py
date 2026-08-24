"""Schema and taxonomy contracts — cheap tests that catch expensive mistakes."""
from __future__ import annotations

from sovereignguard import config as C
from sovereignguard import taxonomy
from sovereignguard.schema import (CUSTOMER_COLUMNS, EVENT_COLUMNS, FEATURE_COLUMNS,
                                   FEATURE_LABELS, LABEL_COLUMNS, MERCHANT_COLUMNS)


def test_feature_columns_unique():
    dupes = {c for c in FEATURE_COLUMNS if FEATURE_COLUMNS.count(c) > 1}
    assert not dupes, f"duplicate feature columns: {dupes}"


def test_every_feature_has_a_human_label():
    missing = [c for c in FEATURE_COLUMNS if c not in FEATURE_LABELS]
    assert not missing, f"features without labels (breaks explanations): {missing}"


def test_no_label_column_is_a_feature():
    leak = set(LABEL_COLUMNS) & set(FEATURE_COLUMNS)
    assert not leak, f"LABEL LEAKAGE in the feature contract: {leak}"


def test_event_and_label_columns_disjoint():
    overlap = set(EVENT_COLUMNS) & set(LABEL_COLUMNS)
    assert not overlap, f"event/label overlap: {overlap}"


def test_taxonomy_validates_against_config():
    taxonomy.validate()


def test_taxonomy_has_all_seven_families():
    entries = taxonomy.attack_entries()
    assert len(entries) == 7, f"expected 7 attack families, got {len(entries)}"
    assert set(taxonomy.by_type()) == set(C.ATTACK_TYPES)


def test_taxonomy_expected_signals_are_real_features():
    feats = set(FEATURE_COLUMNS)
    for a in taxonomy.attack_entries():
        bad = [s for s in a["expected_signals"] if s not in feats]
        assert not bad, f"{a['attack_type']} references non-existent features: {bad}"


def test_taxonomy_entries_are_complete():
    required = ["attack_type", "attack_name", "family", "severity", "target",
                "payment_surfaces", "genai_role", "behavioural_changes",
                "expected_signals", "stages", "hard_variant_note", "mitigations"]
    for a in taxonomy.attack_entries():
        for k in required:
            assert k in a and a[k], f"{a.get('attack_type')} missing '{k}'"
        assert len(a["stages"]) >= 3, f"{a['attack_type']} has too few stages"
        assert len(a["mitigations"]) >= 2, f"{a['attack_type']} needs mitigations"


def test_type_mix_is_a_probability_distribution():
    mix = taxonomy.type_mix()
    assert abs(sum(mix.values()) - 1.0) < 1e-9
    assert all(v > 0 for v in mix.values())


def test_risk_bands_partition_the_range():
    bands = sorted(C.RISK_BANDS, key=lambda b: b.lower)
    assert bands[0].lower == 0.0, "bands must start at 0"
    assert bands[-1].upper > 100.0, "bands must cover 100"
    for a, b in zip(bands, bands[1:]):
        assert abs(a.upper - b.lower) < 1e-9, f"gap or overlap between {a.name}/{b.name}"


def test_personas_and_categories_have_normalisable_weights():
    assert abs(sum(p.weight for p in C.PERSONAS) - 1.0) < 0.02
    assert abs(sum(c.weight for c in C.CATEGORIES) - 1.0) < 0.02
    for p in C.PERSONAS:
        s = sum(p.method_weights.values())
        assert abs(s - 1.0) < 0.02, f"{p.name} method weights sum to {s}"
        s2 = sum(p.category_affinity.values())
        assert abs(s2 - 1.0) < 0.02, f"{p.name} category affinity sums to {s2}"


def test_legit_event_rates_are_non_zero():
    """If honest customers never did these things, the corresponding flags would
    become perfect fraud oracles and every metric would be meaningless."""
    for k, v in C.LEGIT_EVENT_RATES.items():
        assert v > 0, f"LEGIT_EVENT_RATES['{k}'] is zero — creates a label oracle"
