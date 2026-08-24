"""Detection splits, gap analysis, persistence, and the API surface."""
from __future__ import annotations

import dataclasses
import json
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

from conftest import SEED, tiny_detector, tiny_world
from sovereignguard import config as C
from sovereignguard.detection import (Detector, temporal_grouped_split,
                                      unseen_attack_split)
from sovereignguard.evaluation.gap_analysis import HYPOTHESES, analyse_gaps
from sovereignguard.generators.adversarial import ADVERSARIAL_MOVES
from sovereignguard.generators.attacks import KNOBS, Knobs
from sovereignguard.store import Store


# ----------------------------------------------------------------- splits
def test_temporal_split_partitions_all_rows():
    w = tiny_world()
    sp = temporal_grouped_split(w.tx)
    idx = np.concatenate([sp.train, sp.valid, sp.test])
    assert len(idx) == len(w.tx), "splits must cover every row exactly once"
    assert len(set(idx.tolist())) == len(w.tx), "splits overlap"
    for a, b in (("train", "valid"), ("train", "test"), ("valid", "test")):
        assert not (set(getattr(sp, a).tolist()) & set(getattr(sp, b).tolist())), \
            f"{a}/{b} overlap"


def test_no_attack_campaign_spans_two_splits():
    """A 10-event takeover split across train and test leaks the answer."""
    w = tiny_world()
    sp = temporal_grouped_split(w.tx)
    aid = w.tx["attack_id"].to_numpy()
    where = {}
    for name in ("train", "valid", "test"):
        for i in getattr(sp, name):
            a = aid[i]
            if not a:
                continue
            where.setdefault(a, set()).add(name)
    bad = {a: s for a, s in where.items() if len(s) > 1}
    assert not bad, f"CAMPAIGN LEAKAGE: {len(bad)} attacks span splits, e.g. {list(bad)[:3]}"


def test_every_split_has_fraud_to_learn_from():
    w = tiny_world()
    sp = temporal_grouped_split(w.tx)
    y = w.tx["fraud_label"].to_numpy()
    assert y[sp.train].sum() > 5, "training split has almost no positives"
    assert y[sp.test].sum() > 5, "test split has almost no positives"


def test_unseen_split_excludes_holdout_from_training():
    w = tiny_world()
    hold = ["SOCIAL_ENGINEERING"]
    sp = unseen_attack_split(w.tx, hold)
    at = w.tx["attack_type"].to_numpy()
    y = w.tx["fraud_label"].to_numpy()
    for name in ("train", "valid"):
        idx = getattr(sp, name)
        held = np.isin(at[idx], hold) & (y[idx] == 1)
        assert not held.any(), f"held-out family leaked into {name}"
    te = sp.test
    assert (np.isin(at[te], hold) & (y[te] == 1)).any(), "holdout missing from test"
    # a same-threshold reference must remain, or the result is uninterpretable
    assert ((~np.isin(at[te], hold)) & (y[te] == 1)).any(), \
        "no seen-family reference in the test window"


# -------------------------------------------------------------- detection
def test_detector_learns_and_respects_its_budget():
    w = tiny_world()
    det, sp = tiny_detector()
    m = det.metrics["test"]["overall"]
    assert m["roc_auc"] > 0.85, f"ROC-AUC {m['roc_auc']:.4f} too low"
    assert m["recall"] > 0.3, f"recall {m['recall']:.4f} too low"
    assert m["fpr"] <= det.target_fpr * 2.0 + 1e-9, \
        f"realised FPR {m['fpr']:.5f} far above budget {det.target_fpr}"
    assert 0.0 < det.threshold < 1.0


def test_detector_save_load_round_trip():
    w = tiny_world()
    det, sp = tiny_detector()
    sub = w.feats.iloc[:150]
    before = det.predict_proba(sub)
    with tempfile.TemporaryDirectory() as d:
        det.save(Path(d) / "det")
        again = Detector.load(Path(d) / "det")
    np.testing.assert_allclose(before, again.predict_proba(sub), rtol=0, atol=0)
    assert again.threshold == det.threshold
    assert again.feature_names == det.feature_names


def test_explanations_are_well_formed():
    w = tiny_world()
    det, sp = tiny_detector()
    rows = det.explain(w.feats.iloc[:5], top_k=5)
    assert len(rows) == 5
    for r in rows:
        assert 0.0 <= r["fraud_probability"] <= 1.0
        assert 0.0 <= r["risk_score"] <= 100.0
        assert r["action"] in {"ALLOW", "MONITOR", "STEP_UP_AUTH", "HOLD_REVIEW"}
        for item in r["reasons"]:
            assert item["contribution"] > 0, "reasons must be risk-increasing"
            assert item["label"] and item["feature"]
        for item in r["protective_factors"]:
            assert item["contribution"] < 0
        assert det.narrative(r)


def test_decide_returns_a_row_per_transaction():
    w = tiny_world()
    det, _ = tiny_detector()
    out = det.decide(w.feats.iloc[:200])
    assert len(out) == 200
    assert set(out.columns) == {"fraud_probability", "risk_score", "risk_band",
                                "action", "flagged"}
    assert out["flagged"].isin([0, 1]).all()


# ------------------------------------------------------------ gap analysis
def test_gap_report_is_internally_consistent():
    w = tiny_world()
    det, sp = tiny_detector()
    F = w.feats.iloc[sp.test].reset_index(drop=True)
    tx = w.tx.iloc[sp.test].reset_index(drop=True)
    p = det.predict_proba(F)
    g = analyse_gaps(F, tx, p, det.threshold)

    assert g.n_detected + g.n_missed == g.n_attacks
    if g.n_attacks:
        assert abs(g.recall - g.n_detected / g.n_attacks) < 1e-9
    for c in g.causes:
        assert 0.0 <= c["share_of_missed"] <= 1.0, c
        assert 0.0 <= c["share_of_detected"] <= 1.0, c
        assert c["remediation"], f"cause {c['key']} has no remediation"
        assert c["description"]
    total_attr = sum(c["attribution"] for c in g.causes)
    # Attributions are rounded to 4dp for display, so summing N of them can
    # drift by up to N * 5e-5. Allow that slack rather than demanding exactness
    # from values that are deliberately rounded.
    slack = 5e-5 * max(len(g.causes), 1) + 1e-9
    assert total_attr <= 1.0 + slack, f"attribution sums to {total_attr}"
    assert all(c["attribution"] >= 0.0 for c in g.causes), "negative attribution"
    assert g.headline()


def test_priority_knobs_reference_real_knob_fields():
    """Catches typos in ADVERSARIAL_MOVES that would silently no-op."""
    knob_fields = {f.name for f in dataclasses.fields(Knobs)}
    logical = {"amount_mult", "gap", "n_drain", "merchant_reuse",
               "identity_quality", "spread_days"}
    for key, move in ADVERSARIAL_MOVES.items():
        assert move.knob in knob_fields | logical, \
            f"ADVERSARIAL_MOVES['{key}'] targets unknown knob '{move.knob}'"
        assert move.rationale, f"{key} has no rationale"


def test_every_hypothesis_has_a_move_or_is_documented():
    hyp_keys = {h.key for h in HYPOTHESES}
    missing = hyp_keys - set(ADVERSARIAL_MOVES)
    assert not missing, f"gap causes with no adversarial response: {missing}"


def test_adversarial_moves_actually_mutate_the_knobs():
    for key, move in ADVERSARIAL_MOVES.items():
        base = KNOBS["HARD"]
        k = dataclasses.replace(base)
        move.apply(k, 1.0)
        changed = dataclasses.asdict(k) != dataclasses.asdict(base)
        # two moves are handled via the difficulty label rather than a field
        if key not in ("MERCHANT_MIMICRY", "THIN_BUT_CLEAN_IDENTITY"):
            assert changed, f"ADVERSARIAL_MOVES['{key}'] changed nothing"


# ----------------------------------------------------------------- store
def test_store_round_trips_every_table():
    with tempfile.TemporaryDirectory() as d:
        st = Store(path=Path(d) / "t.db", allow_fallback=False)
        st.create_run("r1", "test", {"scale": "nano"}, "nano", SEED)
        assert st.get_run("r1")["status"] == "running"
        st.finish_run("r1", {"n_transactions": 10})
        rec = st.get_run("r1")
        assert rec["status"] == "complete"
        assert rec["summary"]["n_transactions"] == 10
        assert any(r["run_id"] == "r1" for r in st.list_runs())

        st.save_gap("g1", "mr1", {"n_attacks": 5, "n_detected": 3,
                                  "n_missed": 2, "recall": 0.6, "causes": []})
        assert st.latest_gap()["report"]["recall"] == 0.6

        st.save_experiment("e1", "exp1", {"ok": True})
        assert st.get_experiment("e1")["result"]["ok"] is True
        assert len(st.list_experiments()) == 1


def test_store_falls_back_when_the_path_is_unusable():
    st = Store(path=Path("/proc/definitely/not/writable/x.db"))
    assert st.fallback_used, "Store should fall back rather than crash"
    st.create_run("r", "test", {})
    assert st.get_run("r") is not None


# ------------------------------------------------------------------- api
def _free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _serve():
    from sovereignguard.api.server import serve
    port = _free_port()
    httpd = serve("127.0.0.1", port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.4)
    return httpd, f"http://127.0.0.1:{port}"


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=20) as r:
        return r.status, json.loads(r.read())


def _post(base, path, body, raw=None):
    data = raw if raw is not None else json.dumps(body).encode()
    rq = urllib.request.Request(base + path, data=data,
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(rq, timeout=30) as r:
        return r.status, json.loads(r.read())


def test_api_core_endpoints():
    httpd, base = _serve()
    try:
        code, h = _get(base, "/api/health")
        assert code == 200 and h["status"] == "ok"
        assert "ml_backend" in h and "optional_backends" in h

        code, cfg = _get(base, "/api/config")
        assert code == 200
        assert set(cfg["attack_types"]) == set(C.ATTACK_TYPES)
        assert len(cfg["risk_bands"]) == len(C.RISK_BANDS)
        assert cfg["n_features"] > 50

        code, tax = _get(base, "/api/taxonomy")
        assert code == 200 and len(tax["attacks"]) == 7

        code, one = _get(base, "/api/taxonomy/ACCOUNT_TAKEOVER")
        assert code == 200 and one["attack_type"] == "ACCOUNT_TAKEOVER"

        code, runs = _get(base, "/api/runs")
        assert code == 200 and "runs" in runs
    finally:
        httpd.shutdown()


def test_api_error_handling_is_graceful():
    httpd, base = _serve()
    try:
        for path in ("/api/nope", "/api/taxonomy/NOT_A_FAMILY", "/api/jobs/nope"):
            try:
                _get(base, path)
                raise AssertionError(f"{path} should not have succeeded")
            except urllib.error.HTTPError as e:
                assert e.code == 404, f"{path} returned {e.code}, expected 404"

        # malformed JSON must be a 400, not a 500
        try:
            _post(base, "/api/detect", None, raw=b"{not json")
            raise AssertionError("malformed JSON should not have succeeded")
        except urllib.error.HTTPError as e:
            assert e.code == 400, f"malformed body returned {e.code}"

        # a valid request with no world loaded must be a 400, not a crash
        try:
            _post(base, "/api/redteam/generate", {"n_scenarios": 5})
            raise AssertionError("should have refused without a world")
        except urllib.error.HTTPError as e:
            assert e.code == 400, f"expected 400, got {e.code}"
    finally:
        httpd.shutdown()
