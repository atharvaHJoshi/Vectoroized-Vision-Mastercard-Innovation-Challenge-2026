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


def test_clear_simulations_keeps_only_latest_run():
    with tempfile.TemporaryDirectory() as d:
        st = Store(path=Path(d) / "t.db", allow_fallback=False)
        st.create_run("old", "simulate", {}, "nano", 1)
        st.save_gap("g1", "mr_old", {"n_attacks": 5, "n_detected": 3,
                                     "n_missed": 2, "recall": 0.6})
        st.save_experiment("e1", "exp1", {"ok": True})
        st.clear_simulations()
        st.create_run("new", "simulate", {}, "nano", 2)
        assert st.get_run("old") is None
        assert any(r["run_id"] == "new" for r in st.list_runs())
        assert st.query("SELECT COUNT(*) AS n FROM attack_scenarios")[0]["n"] == 0
        assert st.latest_gap() is None
        assert len(st.list_loops()) == 0
        assert st.get_experiment("e1")["result"]["ok"] is True


# ------------------------------------------------------------------- api
def _free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _serve():
    """Each server gets a private AppState + temp database so parallel or
    background processes never fight the testing process over one sqlite file."""
    import tempfile
    from pathlib import Path as _P
    from sovereignguard.api.server import AppState, serve
    from sovereignguard.store import Store
    state = AppState(store=Store(path=_P(tempfile.mkdtemp()) / "test.db"))
    port = _free_port()
    httpd = serve("127.0.0.1", port, state=state)
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


def test_sse_streams_generation_realtime():
    """The realtime stream: progress + per-scenario generation events, then done."""
    httpd, base = _serve()
    try:
        st, job = _post(base, "/api/simulate",
                        {"scale": "nano", "train": False, "persist": False})
        assert st == 202 and job["job_id"]

        events = []                       # (event_name, payload)
        with urllib.request.urlopen(base + "/api/sse/" + job["job_id"], timeout=120) as r:
            ctype = r.headers.get("Content-Type", "")
            assert ctype.startswith("text/event-stream"), ctype
            name = None
            for raw in r:
                line = raw.decode().rstrip("\n")
                if not line.strip():
                    continue
                if line.startswith("event:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    events.append((name, json.loads(line.split(":", 1)[1].strip())))
                    if name == "done":
                        break

        gens = [d for n, d in events if n == "generation"]
        progs = [d for n, d in events if n == "progress"]
        done = [d for n, d in events if n == "done"]
        assert gens, "generation telemetry must stream per scenario"
        assert progs, "at least one progress message expected"
        assert done and done[0].get("run_id"), "done event must carry the run result"
        assert gens[0]["attack_id"] and gens[0]["n_events"] > 0

        run_id = done[0]["run_id"]
        code, rec = _get(base, f"/api/runs/{run_id}")
        assert code == 200
        # every streamed scenario must be findable in the world afterwards
        code, attacks = _post(base, "/api/attacks", {"run_id": run_id, "limit": 2000})
        world_ids = {a["attack_id"] for a in attacks["rows"]}
        streamed_ids = {g["attack_id"] for g in gens}
        assert streamed_ids <= world_ids, "streamed scenarios must have landed in the world"
    finally:
        httpd.shutdown()


def test_sse_unknown_job_emits_error_event():
    httpd, base = _serve()
    try:
        with urllib.request.urlopen(base + "/api/sse/job_nope", timeout=20) as r:
            raw = r.read().decode()
        assert "event: error" in raw and "unknown job" in raw
    finally:
        httpd.shutdown()


def test_search_and_attacks_endpoints(tiny_world, tiny_detector):
    from sovereignguard.api.server import (STATE, h_attacks, h_search)
    w = tiny_world
    rid = "w_search"
    STATE.put_world(rid, w)
    STATE.put_detector("d_search", tiny_detector[0])

    code, att = h_attacks({}, {"run_id": rid})
    assert code == 200 and att["total"] == len(w.batch.scenarios)
    assert att["rows"] and "attack_id" in att["rows"][0]

    aid = w.batch.scenarios["attack_id"].iloc[0]
    code, s = h_search({}, {"run_id": rid, "attack_id": str(aid), "limit": 100})
    assert code == 200
    assert s["total"] == int((w.tx["attack_id"] == aid).sum())
    assert s["scored"] and all("fraud_probability" in r for r in s["rows"])
    assert all(r["attack_id"] == aid for r in s["rows"])

    code, m = h_search({}, {"run_id": rid, "result": "missed", "fraud_only": True})
    assert code == 200
    assert all(r["fraud_label"] == 1 for r in m["rows"])
    assert all(not r["detected"] for r in m["rows"])

    txid_sample = str(w.tx.loc[w.tx["attack_id"] == aid, "transaction_id"].iloc[0])
    code, q = h_search({}, {"run_id": rid, "q": txid_sample[:16]})
    assert code == 200 and q["total"] >= 1

    for h in (h_attacks, h_search):
        code, _ = h({}, {"run_id": "nope"})
        assert code == 400


def test_build_world_emits_generation_telemetry():
    from sovereignguard.pipeline import build_world
    seen = []
    build_world("nano", seed=7, quiet=True, on_scenario=seen.append)
    assert len(seen) > 0, "on_scenario must fire once per baseline scenario"
    first = seen[0]
    assert first["attack_id"] and first["n_events"] > 0
    assert "attack_type" in first and "difficulty" in first and "victim_customer_id" in first
    assert len(seen) == len(set(x["attack_id"] for x in seen)), \
        "baseline has a deterministic per-scenario count; ids must be unique"


def test_attack_anatomy_endpoint(tiny_world, tiny_detector):
    from sovereignguard.api.server import STATE, h_attack_detail
    w = tiny_world
    rid = "w_anat"
    STATE.put_world(rid, w)
    STATE.put_detector("d_anat", tiny_detector[0])

    code, err = h_attack_detail({}, {})
    assert code == 400

    aid = w.batch.scenarios["attack_id"].iloc[0]
    code, r = h_attack_detail({}, {"run_id": rid, "attack_id": str(aid)})
    assert code == 200
    assert r["attack"]["attack_id"] == aid
    assert r["family"] and r["family"]["attack_name"]
    assert r["knobs"], "evasion knobs must be resolved from the difficulty label"
    assert r["events"], "attack events must be spliced into the world stream"
    assert r["scored"] and all("fraud_probability" in e for e in r["events"]), \
        "events must carry model scores when a detector is loaded"
    assert r["timeline"] and any(t["is_attack"] for t in r["timeline"]), \
        "victim timeline must contain the spliced attack"
    tl_follows = r["timeline"]
    assert all(tl_follows[i]["timestamp"] <= tl_follows[i + 1]["timestamp"]
               for i in range(len(tl_follows) - 1)), "timeline must be chronological"

    code, _ = h_attack_detail({}, {"run_id": rid, "attack_id": "ATKNOPE0000_0"})
    assert code == 404


def test_redteam_generate_merges_into_world(tiny_world):
    from sovereignguard.api.server import (STATE, h_redteam_generate, h_search)
    w = tiny_world
    rid = "w_merge"
    STATE.put_world(rid, w)
    STATE.baseline[rid] = w.batch
    before_tx, before_scen = len(w.tx), len(w.batch.scenarios)

    def run_generate(body):
        code, r = h_redteam_generate({}, body)
        assert code == 202 and r["job_id"], \
            "redteam generate must be an async job (202), like simulate/loop"
        t0 = time.time()
        while time.time() - t0 < 120:
            st = STATE.job(r["job_id"])
            if st["status"] in ("complete", "failed"):
                if st["status"] == "failed":
                    raise AssertionError(f"redteam job failed: {st.get('error')}")
                return st["result"]
            time.sleep(0.1)
        raise AssertionError("redteam job did not finish in time")

    r = run_generate({"run_id": rid, "n_scenarios": 5})
    assert r["merged"] is True and r["n_events"] > 0
    w2 = STATE.worlds[rid]
    assert len(w2.tx) == before_tx + r["n_events"]
    assert len(w2.batch.scenarios) == before_scen + r["n_scenarios"]
    assert w2.tx["transaction_id"].nunique() == len(w2.tx), \
        "re-minted ids must not collide with the baseline / each other"

    ids = [e["transaction_id"] for e in r["events_sample"]]
    assert w2.tx["transaction_id"].isin(ids).sum() == len(ids), \
        "newly generated events must land in the world stream"
    code, s = h_search({}, {"run_id": rid, "transaction_id": ids[0]})
    # transaction_id is not a search filter, but search by that id substring:
    code, s = h_search({}, {"run_id": rid, "q": ids[0][:20]})
    assert code == 200 and s["total"] >= 1

    # a second generate replaces the previous ad-hoc batch, baseline stays
    before2 = len(w2.tx)
    r2 = run_generate({"run_id": rid, "n_scenarios": 3})
    w3 = STATE.worlds[rid]
    assert r2["merged"] is True and len(w3.tx) == before2 - r["n_events"] + r2["n_events"], \
        "previous ad-hoc batch is replaced"
    assert w3.tx["transaction_id"].isin(ids).sum() == 0, \
        "previous ad-hoc events must be replaced, not accumulate"


def _wait_job(base, jid, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        code, j = _get(base, f"/api/jobs/{jid}")
        if j["status"] in ("complete", "failed"):
            return j
        time.sleep(0.5)
    raise AssertionError(f"job {jid} did not finish in {timeout}s")


def test_identical_simulate_is_reused_and_endpoints_memoise():
    """The same configuration must not rebuild an 18s world: the second
    simulate returns the cached result, and detect/gap are answered from the
    memo so repeated button presses are instant."""
    httpd, base = _serve()
    try:
        _, j1 = _post(base, "/api/simulate",
                      {"scale": "nano", "train": True, "persist": False})
        r1 = _wait_job(base, j1["job_id"])["result"]

        _, j2 = _post(base, "/api/simulate",
                      {"scale": "nano", "train": True, "persist": False})
        r2 = _wait_job(base, j2["job_id"])["result"]
        assert r2.get("reused") is True, "identical config should reuse the cache"
        assert r2["run_id"] == r1["run_id"]
        assert r2["summary"]["n_transactions"] == r1["summary"]["n_transactions"]

        # a genuinely different configuration must build fresh
        _, j3 = _post(base, "/api/simulate",
                      {"scale": "nano", "train": True, "persist": False,
                       "seed": 9999})
        r3 = _wait_job(base, j3["job_id"])["result"]
        assert r3.get("reused") is not True
        assert r3["run_id"] != r1["run_id"]

        # detect + gap memoise: same answer, second call served instantly
        rid = r1["run_id"]
        _, d1 = _post(base, "/api/detect", {"run_id": rid})
        _, d2 = _post(base, "/api/detect", {"run_id": rid})
        assert d1["n_scored"] == d2["n_scored"] \
            and d1["threshold"] == d2["threshold"]
        _, g1 = _post(base, "/api/gap", {"run_id": rid})
        _, g2 = _post(base, "/api/gap", {"run_id": rid})
        assert g1["n_missed"] == g2["n_missed"]
    finally:
        httpd.shutdown()


def test_cleared_run_row_is_still_readable_while_world_alive():
    """A later persist=True simulate runs clear_simulations(), wiping prior
    runs' DB rows. The dashboard polls /api/runs/{rid} for the run_id a
    completed simulate just returned, so it must keep serving the record from
    the live in-memory world instead of 404ing."""
    httpd, base = _serve()
    try:
        _, j1 = _post(base, "/api/simulate",
                      {"scale": "nano", "train": False, "persist": True})
        r1 = _wait_job(base, j1["job_id"])["result"]
        rid1 = r1["run_id"]

        # a different configuration rebuilds and, with persist=True, clears
        # rid1's database row (but not its in-memory world)
        _, j2 = _post(base, "/api/simulate",
                      {"scale": "nano", "train": False, "persist": True,
                       "target_prevalence": 0.02})
        r2 = _wait_job(base, j2["job_id"])["result"]
        assert r2["run_id"] != rid1

        code, rec1 = _get(base, f"/api/runs/{rid1}")
        assert code == 200, \
            "a run whose world is still in memory must not 404 after its row is cleared"
        assert rec1["summary"]["n_transactions"] > 0

        code, rec2 = _get(base, f"/api/runs/{r2['run_id']}")
        assert code == 200 and rec2["summary"]["n_transactions"] > 0
    finally:
        httpd.shutdown()
