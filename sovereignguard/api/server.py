"""
Backend API (Phase 21).

FastAPI is the framework named in the plan and `app_fastapi.py` provides that
entry point, but it cannot be installed in every environment. This module is
therefore a dependency-free implementation on `http.server` exposing the same
routes and JSON contracts, so `python -m sovereignguard.api.server` always
works with nothing but the standard library.

Routes (all JSON unless noted):

  GET  /api/health                     liveness + backend capability report
  GET  /api/taxonomy                   attack knowledge base (Pillar 1)
  GET  /api/taxonomy/{attack_type}     one attack family in full
  GET  /api/config                     scales, difficulties, risk bands
  GET  /api/runs                       list pipeline runs
  GET  /api/runs/{run_id}              one run + summary
  POST /api/simulate                   build world + train baseline  (async job)
  POST /api/redteam/generate           generate attacks on an existing run
  POST /api/detect                     run detection + metrics on a run
  POST /api/score                      score a single transaction (+explanation)
  POST /api/attacks                    list a run's attack scenarios (picker)
  POST /api/search                     search a run's transactions / attacks
  POST /api/attack                       anatomy of one generated attack
  GET  /api/gap                        latest gap analysis
  POST /api/gap                        recompute gap analysis for a model run
  POST /api/loop                       run the adaptive loop        (async job)
  GET  /api/loop/latest                latest loop result (hero screen)
  GET  /api/models                     model runs + metrics
  GET  /api/experiments                experiment results
  GET  /api/experiments/{id}           one experiment
  GET  /api/jobs/{job_id}              async job status/result
  GET  /api/sse/{job_id}               realtime stream (progress + generation)
  GET  /                               dashboard (static frontend)
"""
from __future__ import annotations

import dataclasses
import errno
import json
import mimetypes
import os
import sys
import threading
import time
import traceback
import uuid
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

from .. import config as C
from .. import taxonomy
from ..detection import Detector, optional_backends, temporal_grouped_split
from ..evaluation.gap_analysis import analyse_gaps
from ..evaluation.metrics import compute_metrics
from ..pipeline import (World, adversarial_loop, build_world, diagnose,
                        train_baseline)
from ..generators.attacks import KNOBS
from ..generators.redteam import AttackBatch
from ..store import Store
from ..schema import FEATURE_COLUMNS, FEATURE_LABELS

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


# ==========================================================================
# In-process state: worlds and detectors are expensive, so keep them warm.
# ==========================================================================
class AppState:
    def __init__(self, store: Optional[Store] = None):
        self.store = store or Store()
        self.worlds: Dict[str, World] = {}
        self.detectors: Dict[str, Detector] = {}
        self.jobs: Dict[str, Dict] = {}
        self.lock = threading.RLock()
        self.default_run: Optional[str] = None
        self.baseline: Dict[str, AttackBatch] = {}
        # Config fingerprint -> completed simulate result. Deterministic worlds
        # mean an identical request can be answered from cache almost instantly.
        self.world_cache: Dict[str, Dict] = {}
        # Expensive pure read endpoints (detect, gap) memoised per
        # (run, resolved detector) so repeated button presses are instant.
        self.memo: Dict[Tuple[str, str, str], Tuple[float, Dict]] = {}

    def memo_get(self, kind: str, run_id: str, detkey: str,
                 ttl: float = 600.0) -> Optional[Dict]:
        k = (kind, run_id, detkey or "")
        hit = self.memo.get(k)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        return None

    def memo_set(self, kind: str, run_id: str, detkey: str, payload: Dict) -> None:
        if len(self.memo) > 64:
            self.memo.clear()
        self.memo[(kind, run_id, detkey or "")] = (time.time(), payload)

    def resolve_detector_key(self, key: Optional[str]) -> Optional[str]:
        """The registry key a request actually resolves to (used to memoise)."""
        with self.lock:
            if not key:
                return None
            if key in self.detectors:
                return key
            for suffix in ("hardened", "baseline"):
                k = f"{key}:{suffix}"
                if k in self.detectors:
                    return k
            return None

    # ---- snapshot seeding
    def seed_snapshot(self, directory=None) -> Optional[Dict]:
        """Restore a persisted world + detector into memory.

        Called at server boot so the dashboard opens fully populated instead of
        waiting for the first "Build". A no-op (returns None) when no snapshot
        exists, so the server still boots fine from a clean checkout.
        """
        from ..snapshot import has_snapshot, load_snapshot
        if not has_snapshot(directory):
            return None
        world, det, meta = load_snapshot(directory)
        run_id = str(meta.get("run_id") or "seed")
        model_kind = str(det.train_meta.get("model_kind", "gbdt"))

        with self.lock:
            self.worlds[run_id] = world
            self.baseline[run_id] = world.batch
            self.detectors[f"{run_id}:baseline"] = det
            self.detectors[f"{run_id}:hardened"] = det
            self.default_run = run_id

            cfg = {"scale": meta.get("scale"), "seed": meta.get("seed"),
                   "target_prevalence": meta.get("target_prevalence"),
                   "attack_types": meta.get("attack_types"),
                   "model_kind": model_kind, "source": "snapshot"}
            self.store.create_run(run_id, "simulate", cfg,
                                  str(meta.get("scale", "")),
                                  int(meta.get("seed") or 0))
            self.store.save_world(run_id, world)
            mr = f"mr_snapshot_{int(meta.get('created_at', 0))}"
            self.store.save_model_run(mr, run_id, det, "baseline (snapshot)")
            self.store.finish_run(run_id, world.summary())

            # Pre-warm the world cache so a "New simulation" with the snapshot's
            # own configuration returns instantly (identical deterministic world).
            from ..snapshot import snapshot_config_fingerprint
            fp = snapshot_config_fingerprint(meta)
            self.world_cache[fp] = {
                "run_id": run_id,
                "result": {
                    "run_id": run_id,
                    "summary": world.summary(),
                    "generation": {"count": 0, "attacks": []},
                    "detector_key": f"{run_id}:baseline",
                    "model_run_id": mr,
                    "threshold": det.threshold,
                    "metrics": det.metrics.get("test", {}),
                    "train_meta": det.train_meta,
                    "top_features": det.metrics.get("top_features", []),
                },
                "attacks": [],
            }
        return {"run_id": run_id, "summary": world.summary(),
                "n_transactions": int(len(world.tx)),
                "n_attack_scenarios": int(world.batch.n_scenarios),
                "detector_key": f"{run_id}:baseline"}

    # ---- jobs
    def start_job(self, kind: str, fn: Callable[[Callable[[str], None]], Dict],
                  feed: Optional[List] = None) -> str:
        job_id = f"job_{uuid.uuid4().hex[:10]}"
        with self.lock:
            self.jobs[job_id] = {"job_id": job_id, "kind": kind, "status": "running",
                                 "created_at": time.time(), "progress": [],
                                 "result": None, "error": None}
            if feed is not None:
                self.jobs[job_id]["feed"] = feed

        def note(msg: str) -> None:
            with self.lock:
                self.jobs[job_id]["progress"].append(
                    {"t": round(time.time(), 3), "message": msg})

        def run() -> None:
            try:
                result = fn(note)
                with self.lock:
                    self.jobs[job_id].update(status="complete", result=result,
                                             finished_at=time.time())
            except Exception as exc:                       # pragma: no cover
                with self.lock:
                    self.jobs[job_id].update(
                        status="failed", error=f"{type(exc).__name__}: {exc}",
                        traceback=traceback.format_exc(), finished_at=time.time())

        threading.Thread(target=run, daemon=True).start()
        return job_id

    def job(self, job_id: str) -> Optional[Dict]:
        with self.lock:
            j = self.jobs.get(job_id)
            return dict(j) if j else None

    # A job feed is a shared list the worker appends to as it produces items
    # (e.g. per-scenario generation telemetry). SSE readers walk it by index.
    def job_feed(self, job_id: str, offset: int) -> Tuple[List, int]:
        with self.lock:
            j = self.jobs.get(job_id)
            items = list((j.get("feed") or [])[offset:]) if j else []
            total = len((j.get("feed") or [])) if j else 0
            return items, total

    # ---- worlds
    def put_world(self, run_id: str, world: World) -> None:
        with self.lock:
            self.worlds[run_id] = world
            self.default_run = run_id

    def get_world(self, run_id: Optional[str]) -> Optional[World]:
        with self.lock:
            rid = run_id or self.default_run
            return self.worlds.get(rid) if rid else None

    def put_detector(self, key: str, det: Detector) -> None:
        with self.lock:
            self.detectors[key] = det

    def get_detector(self, key: Optional[str]) -> Optional[Detector]:
        with self.lock:
            if key:
                if key in self.detectors:
                    return self.detectors[key]
                # A bare run_id must resolve to that run's own model, never to
                # another run's: prefer the hardened detector once a loop for
                # this run has replaced the baseline, else the baseline itself.
                for suffix in ("hardened", "baseline"):
                    k = f"{key}:{suffix}"
                    if k in self.detectors:
                        return self.detectors[k]
            if self.detectors:
                return list(self.detectors.values())[-1]
            return None


STATE = AppState()


# ==========================================================================
# Handlers. Each returns (status_code, payload_dict).
# ==========================================================================
def h_health(_q: Dict, _b: Dict) -> Tuple[int, Dict]:
    with STATE.lock:
        worlds = list(STATE.worlds)
        dets = list(STATE.detectors)
    return 200, {
        "status": "ok",
        "service": "sovereignguard",
        "version": __import__("sovereignguard").__version__,
        "time": time.time(),
        "ml_backend": "builtin-numpy (histogram GBDT / RF / TreeSHAP)",
        "optional_backends": optional_backends(),
        "loaded_worlds": worlds,
        "loaded_detectors": dets,
        "default_run": STATE.default_run,
        "frontend_present": FRONTEND_DIR.exists(),
    }


def h_config(_q: Dict, _b: Dict) -> Tuple[int, Dict]:
    return 200, {
        "scales": {k: {"name": v.name, "n_customers": v.n_customers,
                       "n_merchants": v.n_merchants, "n_days": v.n_days,
                       "approx_transactions": v.approx_transactions}
                   for k, v in C.SCALES.items()},
        "default_scale": C.DEFAULT_SCALE,
        "attack_types": C.ATTACK_TYPES,
        "difficulties": C.DIFFICULTIES,
        "difficulty_descriptions": taxonomy.difficulty_levels(),
        "risk_bands": [{"name": b.name, "lower": b.lower, "upper": b.upper,
                        "action": b.action, "description": b.description}
                       for b in C.RISK_BANDS],
        "target_fpr_budget": C.TARGET_FPR_BUDGET,
        "n_features": len(FEATURE_COLUMNS),
        "feature_labels": FEATURE_LABELS,
        "seed": C.SEED,
    }


def h_taxonomy(_q: Dict, _b: Dict) -> Tuple[int, Dict]:
    tx = taxonomy.load_taxonomy()
    return 200, {"version": tx["version"], "description": tx["description"],
                 "genai_amplification_note": tx["genai_amplification_note"],
                 "difficulty_levels": tx["difficulty_levels"],
                 "cross_cutting_patterns": tx["cross_cutting_patterns"],
                 "attacks": taxonomy.summary_table()}


def h_taxonomy_one(attack_type: str) -> Tuple[int, Dict]:
    try:
        return 200, taxonomy.get(attack_type)
    except KeyError as e:
        return 404, {"error": str(e)}


def h_runs(_q: Dict, _b: Dict) -> Tuple[int, Dict]:
    return 200, {"runs": STATE.store.list_runs(), "default_run": STATE.default_run,
                 "in_memory": list(STATE.worlds)}


def h_run_one(run_id: str) -> Tuple[int, Dict]:
    rec = STATE.store.get_run(run_id)
    if not rec:
        # The world may still be alive in memory even though its DB row was
        # cleared by a later persist=True simulation (clear_simulations wipes
        # every prior run's row). The dashboard polls /api/runs/{rid} for the
        # run_id a completed simulate just returned, so serve a record built
        # from the live world instead of 404ing.
        w = STATE.get_world(run_id)
        if w is None:
            return 404, {"error": f"unknown run {run_id}"}
        return 200, {"run_id": run_id, "kind": "simulate", "status": "complete",
                     "config": {}, "summary": w.summary(),
                     "live_summary": w.summary()}
    w = STATE.get_world(run_id)
    if w is not None:
        rec["live_summary"] = w.summary()
    return 200, rec


# --------------------------------------------------------------------------
def h_simulate(_q: Dict, body: Dict) -> Tuple[int, Dict]:
    """Build a world and train the baseline detector (async)."""
    scale = str(body.get("scale", "tiny"))
    if scale not in C.SCALES:
        return 400, {"error": f"unknown scale {scale}", "choices": sorted(C.SCALES)}
    seed = int(body.get("seed", C.SEED))
    prevalence = float(body.get("target_prevalence", 0.010))
    model_kind = str(body.get("model_kind", "gbdt"))
    attack_types = body.get("attack_types") or None
    difficulty_mix = body.get("difficulty_mix") or None
    train = bool(body.get("train", True))
    persist = bool(body.get("persist", True))
    attacks: List[Dict] = []

    # Deterministic world per configuration: the same request is the same
    # world, so an identically-configured simulate can reuse the cached result
    # instead of rebuilding (~18s) and returning in milliseconds.
    fp = json.dumps({"scale": scale, "seed": seed,
                     "target_prevalence": prevalence, "model_kind": model_kind,
                     "train": train, "persist": persist,
                     "attack_types": sorted(attack_types) if attack_types else None,
                     "difficulty_mix": sorted(difficulty_mix) if difficulty_mix else None},
                    sort_keys=True)

    def work(note) -> Dict:
        cached = STATE.world_cache.get(fp)
        if cached:
            note("identical configuration already built — reusing cached world")
            for a in cached["attacks"]:
                attacks.append(a)
            out = dict(cached["result"])
            out["reused"] = True
            out["reused_from"] = cached["run_id"]
            note("done")
            return out

        note(f"building world at scale={scale}")
        world = build_world(scale, seed, target_prevalence=prevalence,
                            attack_types=attack_types,
                            difficulty_mix=difficulty_mix, quiet=True,
                            on_scenario=attacks.append)
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        cfg = {"scale": scale, "seed": seed, "target_prevalence": prevalence,
               "attack_types": attack_types, "difficulty_mix": difficulty_mix,
               "model_kind": model_kind}
        if persist:
            note("clearing prior simulation data (only the new world stays)")
            STATE.store.clear_simulations()
        STATE.store.create_run(run_id, "simulate", cfg, scale, seed)
        STATE.put_world(run_id, world)
        STATE.baseline[run_id] = world.batch
        note(f"world ready: {len(world.tx):,} transactions, "
             f"prevalence {world.y.mean():.4%}")
        out = {"run_id": run_id, "summary": world.summary(),
               "generation": {"count": len(attacks), "attacks": attacks[:2000],
                              "truncated": len(attacks) > 2000}}

        if persist:
            note("persisting to database")
            STATE.store.save_world(run_id, world)

        if train:
            note(f"training {model_kind} detector")
            det, split = train_baseline(world, model_kind, quiet=True)
            key = f"{run_id}:baseline"
            STATE.put_detector(key, det)
            mr = f"mr_{uuid.uuid4().hex[:8]}"
            STATE.store.save_model_run(mr, run_id, det, "baseline")
            note("scoring test window")
            dec = det.decide(world.feats.iloc[split.test])
            tx_te = world.tx.iloc[split.test].reset_index(drop=True)
            STATE.store.save_risk_scores(mr, tx_te, dec)
            STATE.store.save_attack_results(
                mr, tx_te, dec["fraud_probability"].to_numpy(), det.threshold)
            gap, _ = diagnose(world, det, split)
            gid = f"gap_{uuid.uuid4().hex[:8]}"
            STATE.store.save_gap(gid, mr, gap.to_dict())
            out.update({"detector_key": key, "model_run_id": mr, "gap_id": gid,
                        "metrics": det.metrics.get("test", {}),
                        "threshold": det.threshold,
                        "train_meta": det.train_meta,
                        "top_features": det.metrics.get("top_features", []),
                        "gap_headline": gap.headline()})
        STATE.store.finish_run(run_id, out.get("summary", {}))
        STATE.world_cache[fp] = {"run_id": run_id, "result": dict(out),
                                 "attacks": list(attacks)}
        note("done")
        return out

    return 202, {"job_id": STATE.start_job("simulate", work, feed=attacks),
                 "status": "running"}


def _remint_adhoc(batch: AttackBatch, base: int = 5_000_000) -> AttackBatch:
    """Give a freshly generated batch unique attack ids before splicing.

    ``RedTeam.generate`` numbers scenarios from ``000000`` on every call, so a
    second batch would reuse the baseline attack ids — and the transaction /
    session ids that embed them. Re-mint into a private, collision-free range.
    """
    sc = batch.scenarios
    if sc is None or not len(sc):
        return batch
    renames = {}
    nids = []
    for i, row in sc.iterrows():
        old = str(row["attack_id"])
        new = f"{str(row['attack_type'])[:3]}{str(row['difficulty'])[:1]}{base + i:06d}"
        if old != new:
            renames[old] = new
        nids.append(new)
    if not renames:
        return batch
    ev = batch.events.copy()
    sc2 = sc.copy()
    for old, new in renames.items():
        for df in (ev, sc2):
            for col in ("transaction_id", "session_id", "attack_id",
                        "campaign_id"):
                if col in df:
                    df[col] = df[col].astype(str).str.replace(
                        old, new, regex=False)
    sc2["attack_id"] = nids
    return AttackBatch(events=ev, extra_customers=batch.extra_customers,
                       extra_merchants=batch.extra_merchants, scenarios=sc2,
                       request=batch.request)


def h_redteam_generate(_q: Dict, body: Dict) -> Tuple[int, Dict]:
    """Generate attacks against an existing world and splice them in (async).

    The Red Team Simulator used to return a preview only — the generated events
    lived nowhere, so a transaction id shown on the page could not be looked up
    or explained afterwards. The new batch is now re-minted into a unique id
    space, merged into the live world (features recomputed), and becomes fully
    searchable / scorable. The previous ad-hoc batch is replaced each call; the
    baseline (simulation) attacks are preserved.

    Generation + feature rebuild takes ~40s on a demo-scale world, which the
    Next dev proxy aborts at a 30s upstream cap (the browser would see a bare
    "Internal Server Error"). Like /api/simulate and /api/loop this returns a
    job_id immediately; the client polls /api/jobs/{id} (or streams GET
    /api/sse/{id}) and shows progress lines while the work runs.
    """
    rid = body.get("run_id") or STATE.default_run
    world = STATE.get_world(rid)
    if world is None:
        return 400, {"error": "no world loaded; POST /api/simulate first"}
    n = int(body.get("n_scenarios", 200))
    if not 1 <= n <= 20000:
        return 400, {"error": "n_scenarios must be 1..20000"}
    atypes = body.get("attack_types") or None
    if atypes:
        bad = set(atypes) - set(C.ATTACK_TYPES)
        if bad:
            return 400, {"error": f"unknown attack types {sorted(bad)}"}
    difficulty = body.get("difficulty")
    mix = ({difficulty: 1.0} if difficulty else body.get("difficulty_mix")) or None

    def work(note: Callable[[str], None]) -> Dict:
        w = STATE.get_world(rid)
        if w is None:
            raise RuntimeError(f"world {rid} disappeared before generation started")
        note(f"generating {n} scenarios"
             f" ({', '.join(sorted(atypes)) if atypes else 'all families'})")
        pct_seen = {"last": 0}

        def tick(_a: Dict) -> None:
            pct_seen["tick"] = pct_seen.get("tick", 0) + 1
            pct = pct_seen["tick"] * 100 // max(1, n)
            if pct >= pct_seen["last"] + 10:
                pct_seen["last"] = pct
                note(f"generated {pct_seen['tick']}/{n} scenarios ({pct}%)")

        batch = _remint_adhoc(w.red_team.generate(
            n, attack_types=atypes, difficulty_mix=mix,
            stream=f"api:{uuid.uuid4().hex[:6]}", on_scenario=tick),
            base=5_000_000 + int(len(w.tx)))
        base = STATE.baseline.get(rid)
        merged = base is not None and not base.scenarios.empty
        if merged:
            note("merging into world and recomputing behavioural features")
            w = w.rebuild_with([base, batch])
            STATE.put_world(rid, w)
        note("done")
        scen = batch.scenarios
        return {
            "n_scenarios": batch.n_scenarios,
            "n_events": batch.n_events,
            "merged": merged,
            "world_transactions": int(len(w.tx)),
            "world_attack_scenarios": int(len(w.batch.scenarios)),
            "diversity": batch.diversity_report(),
            "scenarios_sample": scen.head(25).to_dict("records") if not scen.empty else [],
            "events_sample": (batch.events.head(25)[
                ["transaction_id", "customer_id", "timestamp", "amount",
                 "payment_method", "transaction_type", "city", "attack_type",
                 "attack_stage", "difficulty"]].to_dict("records")
                if not batch.events.empty else []),
            "by_type": (scen["attack_type"].value_counts().to_dict()
                        if not scen.empty else {}),
            "by_difficulty": (scen["difficulty"].value_counts().to_dict()
                              if not scen.empty else {}),
        }

    return 202, {"job_id": STATE.start_job("redteam", work),
                 "status": "running"}


def h_detect(_q: Dict, body: Dict) -> Tuple[int, Dict]:
    """Run the Blue Team over a run's test window and return full metrics."""
    world = STATE.get_world(body.get("run_id"))
    detkey = STATE.resolve_detector_key(body.get("detector_key")
                                        or body.get("run_id"))
    det = STATE.get_detector(detkey)
    if world is None or det is None:
        return 400, {"error": "need a loaded world and detector; POST /api/simulate"}
    memo_key = detkey or f"$id:{id(det)}"
    cached = STATE.memo_get("detect", body.get("run_id") or "", memo_key)
    if cached:
        return 200, cached
    split = temporal_grouped_split(world.tx)
    idx = split.test
    F = world.feats.iloc[idx].reset_index(drop=True)
    tx = world.tx.iloc[idx].reset_index(drop=True)
    y = tx["fraud_label"].to_numpy().astype(int)
    t0 = time.perf_counter()
    p = det.predict_proba(F)
    latency_us = (time.perf_counter() - t0) * 1e6 / max(1, len(F))
    m = compute_metrics(y, p, det.threshold, amounts=tx["amount"].to_numpy(),
                        latency_us_per_txn=latency_us)
    ev = det.evaluate(F, y, amounts=tx["amount"].to_numpy(),
                      groups={"attack_type": tx["attack_type"].to_numpy(),
                              "difficulty": tx["difficulty"].to_numpy()})
    payload = {
        "overall": m.to_dict(),
        "by_attack_type": ev.get("by_attack_type", []),
        "by_difficulty": ev.get("by_difficulty", []),
        "operating_curve": ev["operating_curve"],
        "risk_distribution": ev["risk_distribution"],
        "friction": ev["friction"],
        "threshold": det.threshold,
        "target_fpr": det.target_fpr,
        "top_features": det.metrics.get("top_features", []),
        "n_scored": int(len(F)),
    }
    STATE.memo_set("detect", body.get("run_id") or "", memo_key, payload)
    return 200, payload


def h_score(_q: Dict, body: Dict) -> Tuple[int, Dict]:
    """Score one transaction from a run and explain the decision."""
    world = STATE.get_world(body.get("run_id"))
    det = STATE.get_detector(body.get("detector_key") or body.get("run_id"))
    if world is None or det is None:
        return 400, {"error": "need a loaded world and detector"}

    txid = body.get("transaction_id")
    if txid:
        loc = world.tx.index[world.tx["transaction_id"] == txid]
        if len(loc) == 0:
            return 404, {"error": f"unknown transaction_id {txid}"}
        i = int(loc[0])
    elif body.get("worst_missed"):
        p_all = det.predict_proba(world.feats)
        y = world.y
        cand = np.where((y == 1) & (p_all < det.threshold))[0]
        if len(cand) == 0:
            return 404, {"error": "no missed attacks to show"}
        i = int(cand[np.argmin(p_all[cand])])
    else:
        i = int(body.get("index", 0))
    if not 0 <= i < len(world.tx):
        return 400, {"error": "index out of range"}

    row = world.feats.iloc[[i]]
    expl = det.explain(row, top_k=int(body.get("top_k", 6)))[0]
    txr = world.tx.iloc[i]
    return 200, {
        "transaction": {k: (float(txr[k]) if isinstance(txr[k], (int, float, np.floating,
                                                                np.integer)) else str(txr[k]))
                        for k in ("transaction_id", "customer_id", "merchant_id",
                                  "timestamp", "amount", "payment_method", "channel",
                                  "transaction_type", "city", "auth_result",
                                  "fraud_label", "attack_type", "attack_id",
                                  "attack_stage", "difficulty")},
        "decision": {k: expl[k] for k in ("fraud_probability", "risk_score",
                                          "risk_band", "action")},
        "explanation": expl,
        "narrative": det.narrative(expl),
        "is_correct": bool((expl["fraud_probability"] >= det.threshold) ==
                           bool(txr["fraud_label"])),
    }


_TXROW_KEYS = ("transaction_id", "customer_id", "merchant_id", "amount",
               "payment_method", "channel", "transaction_type", "city",
               "auth_result", "fraud_label", "attack_type", "attack_id",
               "attack_stage", "difficulty", "timestamp")


def _tx_rows(world, idxs) -> List[Dict]:
    tx = world.tx
    out = []
    for i in idxs:
        v = tx.iloc[i]
        row: Dict = {"row_index": int(i)}
        for k in _TXROW_KEYS:
            x = v[k]
            row[k] = float(x) if isinstance(x, (int, float, np.integer,
                                                np.floating)) else str(x)
        out.append(row)
    return out


def h_attacks(_q: Dict, body: Dict) -> Tuple[int, Dict]:
    """List the attack scenarios generated for a run (scenario picker)."""
    world = STATE.get_world(body.get("run_id"))
    if world is None:
        return 400, {"error": "no world loaded; POST /api/simulate first"}
    sc = world.batch.scenarios
    if sc is None or sc.empty:
        return 200, {"total": 0, "limit": 0, "rows": [], "filters": dict(body)}
    mask = pd.Series(True, index=sc.index)
    for key in ("attack_type", "difficulty"):
        val = body.get(key)
        if val:
            mask &= (sc[key] == val)
    q = str(body.get("q") or "").strip()
    if q:
        hay = sc[["attack_id", "campaign_id", "victim_customer_id",
                  "stages"]].astype(str)
        mask &= hay.apply(lambda s: s.str.contains(q, case=False,
                                                   regex=False)).any(axis=1)
    df = sc[mask.to_numpy()]
    limit = int(min(max(body.get("limit", 250), 1), 2000))
    rows = df.head(limit).to_dict("records")
    return 200, {"total": int(len(df)), "limit": limit, "rows": rows,
                 "filters": {k: body.get(k)
                             for k in ("attack_type", "difficulty", "q")}}


def h_search(_q: Dict, body: Dict) -> Tuple[int, Dict]:
    """Search a run's transactions (e.g. the events of one generated attack)
    and optionally score the matches so the weakest events are obvious."""
    world = STATE.get_world(body.get("run_id"))
    if world is None:
        return 400, {"error": "no world loaded; POST /api/simulate first"}
    tx = world.tx
    mask = np.ones(len(tx), dtype=bool)
    for key in ("attack_id", "attack_type", "difficulty"):
        val = body.get(key)
        if val:
            mask &= (tx[key] == val).to_numpy()
    if body.get("fraud_only"):
        mask &= (tx["fraud_label"] == 1).to_numpy()
    q = str(body.get("q") or "").strip()
    if q:
        hay = tx[["transaction_id", "attack_id", "customer_id",
                  "attack_type"]].astype(str)
        mask &= hay.apply(lambda s: s.str.contains(q, case=False,
                                                   regex=False)).any(axis=1).to_numpy()
    idxs = np.where(mask)[0]

    empty = {"total": 0, "offset": 0, "limit": 0, "scored": False,
             "threshold": None, "rows": [], "filters": dict(body)}
    if len(idxs) == 0:
        return 200, empty

    det = STATE.get_detector(body.get("detector_key") or body.get("run_id"))
    result_wanted = str(body.get("result", "any"))
    probs = None
    if det is not None and len(idxs) <= 5000:
        probs = det.predict_proba(world.feats.iloc[idxs])
        if result_wanted == "missed":
            keep = (probs < det.threshold) & (
                tx["fraud_label"].to_numpy()[idxs] == 1)
            idxs, probs = idxs[keep], probs[keep]
        elif result_wanted == "caught":
            keep = (probs >= det.threshold) & (
                tx["fraud_label"].to_numpy()[idxs] == 1)
            idxs, probs = idxs[keep], probs[keep]
    elif result_wanted in ("missed", "caught"):
        return 400, {"error": "result=missed/caught needs a loaded detector"}
    if len(idxs) == 0:
        return 200, empty

    limit = int(min(max(body.get("limit", 100), 1), 500))
    offset = int(max(body.get("offset", 0), 0))
    window = idxs[offset:offset + limit]
    rows = _tx_rows(world, window)
    if probs is not None:
        p = probs[np.arange(offset, offset + len(window))]
        if body.get("sort") == "score":
            order = np.argsort(p)
            rows = [rows[j] for j in order]
            p = p[order]
        for i, row in enumerate(rows):
            row["fraud_probability"] = float(p[i])
            row["detected"] = bool(p[i] >= det.threshold)
    elif body.get("sort") == "score":
        return 400, {"error": "sort=score needs a loaded detector"}
    return 200, {"total": int(len(idxs)), "offset": offset, "limit": limit,
                 "scored": probs is not None,
                 "threshold": float(det.threshold) if det else None,
                 "rows": rows, "filters": dict(body)}


def h_attack_detail(_q: Dict, body: Dict) -> Tuple[int, Dict]:
    """Anatomy of a generated attack: how it was built on its victim.

    Returns the scenario record, the evasion knobs behind its difficulty, the
    family playbook from the taxonomy, every event of the attack spliced into
    the world (with model score when a detector is loaded), and the victim's
    surrounding timeline so the splice is visible.
    """
    world = STATE.get_world(body.get("run_id"))
    if world is None:
        return 400, {"error": "no world loaded; POST /api/simulate first"}
    aid = str(body.get("attack_id") or "")
    if not aid:
        return 400, {"error": "attack_id is required"}
    sc = world.batch.scenarios
    if sc is None or sc.empty:
        return 404, {"error": "no attacks generated yet"}
    match = sc[sc["attack_id"] == aid]
    if match.empty:
        return 404, {"error": f"unknown attack_id {aid}"}
    row = match.iloc[0]
    atype = str(row["attack_type"])
    diff = str(row["difficulty"])
    cid = str(row["victim_customer_id"])

    ev = world.tx[world.tx["attack_id"] == aid].sort_values("timestamp")
    det = STATE.get_detector(body.get("detector_key") or body.get("run_id"))
    probs = None
    if det is not None and len(ev):
        probs = det.predict_proba(world.feats.iloc[ev.index.to_numpy()])
    events = []
    for i, r in enumerate(ev.itertuples(index=False)):
        events.append({
            "transaction_id": str(r.transaction_id),
            "timestamp": int(r.timestamp),
            "amount": float(r.amount),
            "attack_stage": str(r.attack_stage),
            "payment_method": str(r.payment_method),
            "channel": str(r.channel),
            "transaction_type": str(r.transaction_type),
            "device_id": str(r.device_id),
            "city": str(r.city),
            "fraud_probability": float(probs[i]) if probs is not None else None,
            "detected": bool(probs[i] >= det.threshold) if probs is not None else None,
        })

    lo = int(ev["timestamp"].min()) if len(ev) else 0
    hi = int(ev["timestamp"].max()) if len(ev) else 0
    span = int(max(row["span_seconds"], 1))
    pad = int(max(span // 2, 3600))
    w = (world.tx["customer_id"] == cid) & (
        world.tx["timestamp"] >= lo - pad) & (world.tx["timestamp"] <= hi + pad)
    tl = world.tx[w].sort_values(["timestamp", "transaction_id"])
    timeline = []
    for r in tl.itertuples(index=False):
        is_atk = int(r.fraud_label) == 1 and str(r.attack_id) == aid
        timeline.append({
            "transaction_id": str(r.transaction_id),
            "timestamp": int(r.timestamp),
            "amount": float(r.amount),
            "fraud_label": int(r.fraud_label),
            "attack_type": str(r.attack_type) if int(r.fraud_label) == 1 else "NONE",
            "attack_stage": str(r.attack_stage) if is_atk else "",
            "is_attack": bool(is_atk),
        })

    fam = taxonomy.get(atype)
    kn = KNOBS.get(diff)
    knobs = dataclasses.asdict(kn) if kn else {}
    for k, v in knobs.items():
        if isinstance(v, tuple):
            knobs[k] = list(v)
    return 200, {
        "attack": {
            "attack_id": aid, "attack_type": atype, "difficulty": diff,
            "victim_customer_id": cid, "persona": str(row["persona"]),
            "n_events": int(row["n_events"]), "total_value": float(row["total_value"]),
            "max_event_value": float(row["max_event_value"]),
            "span_seconds": int(row["span_seconds"]),
            "stages": str(row["stages"]), "severity": str(row["severity"]),
            "campaign_id": str(row["campaign_id"]),
        },
        "family": {k: fam.get(k) for k in (
            "attack_name", "family", "severity", "target", "genai_role",
            "stages", "behavioural_changes", "expected_signals",
            "hard_variant_note", "mitigations")},
        "knobs": knobs,
        "events": events,
        "timeline": timeline,
        "scored": probs is not None,
    }


def h_gap_get(_q: Dict, _b: Dict) -> Tuple[int, Dict]:
    rec = STATE.store.latest_gap()
    if not rec:
        return 404, {"error": "no gap analysis yet; run /api/simulate"}
    return 200, rec


def h_gap_post(_q: Dict, body: Dict) -> Tuple[int, Dict]:
    world = STATE.get_world(body.get("run_id"))
    detkey = STATE.resolve_detector_key(body.get("detector_key")
                                        or body.get("run_id"))
    det = STATE.get_detector(detkey)
    if world is None or det is None:
        return 400, {"error": "need a loaded world and detector"}
    memo_key = detkey or f"$id:{id(det)}"
    cached = STATE.memo_get("gap", body.get("run_id") or "", memo_key)
    if cached:
        return 200, cached
    split = temporal_grouped_split(world.tx)
    gap, _ = diagnose(world, det, split, on=str(body.get("on", "test")))
    gid = f"gap_{uuid.uuid4().hex[:8]}"
    STATE.store.save_gap(gid, body.get("model_run_id", "adhoc"), gap.to_dict())
    payload = {"gap_id": gid, "headline": gap.headline(), **gap.to_dict()}
    STATE.memo_set("gap", body.get("run_id") or "", memo_key, payload)
    return 200, payload


def h_loop(_q: Dict, body: Dict) -> Tuple[int, Dict]:
    """The hero action: diagnose, adapt, retrain, retest (async)."""
    world = STATE.get_world(body.get("run_id"))
    det = STATE.get_detector(body.get("detector_key") or body.get("run_id"))
    if world is None or det is None:
        return 400, {"error": "need a loaded world and detector; POST /api/simulate"}
    n_adv = int(body.get("n_adversarial", 200))
    use_search = bool(body.get("use_search", True))
    rounds = int(body.get("search_rounds", 2))
    intensity = float(body.get("intensity", 0.85))
    model_kind = str(body.get("model_kind", "gbdt"))
    run_id = body.get("run_id") or STATE.default_run or "unknown"

    def work(note) -> Dict:
        note("diagnosing deployed detector")
        split = temporal_grouped_split(world.tx)
        res, det2, w2 = adversarial_loop(
            world, det, split, n_adversarial=n_adv, model_kind=model_kind,
            use_search=use_search, search_rounds=rounds, intensity=intensity,
            quiet=True)
        key = f"{run_id}:hardened"
        STATE.put_detector(key, det2)
        mr = f"mr_{uuid.uuid4().hex[:8]}"
        STATE.store.save_model_run(mr, run_id, det2, "hardened")
        lid = f"loop_{uuid.uuid4().hex[:8]}"
        STATE.store.save_loop(lid, run_id, res)
        note(res.headline())
        out = res.to_dict()
        out.update({"loop_id": lid, "hardened_detector_key": key,
                    "hardened_model_run_id": mr, "headline": res.headline()})
        return out

    return 202, {"job_id": STATE.start_job("loop", work), "status": "running"}


def h_loop_latest(_q: Dict, _b: Dict) -> Tuple[int, Dict]:
    rec = STATE.store.latest_loop()
    if not rec:
        return 404, {"error": "no loop result yet; POST /api/loop"}
    return 200, rec


def h_models(_q: Dict, _b: Dict) -> Tuple[int, Dict]:
    return 200, {"model_runs": STATE.store.list_model_runs(),
                 "loaded": list(STATE.detectors)}


def h_experiments(_q: Dict, _b: Dict) -> Tuple[int, Dict]:
    return 200, {"experiments": STATE.store.list_experiments()}


def h_experiment_one(eid: str) -> Tuple[int, Dict]:
    rec = STATE.store.get_experiment(eid)
    if not rec:
        return 404, {"error": f"unknown experiment {eid}"}
    return 200, rec


def h_job(job_id: str) -> Tuple[int, Dict]:
    j = STATE.job(job_id)
    if not j:
        return 404, {"error": f"unknown job {job_id}"}
    return 200, j


# ==========================================================================
# Realtime event stream. The frontend opens GET /api/sse/{job_id} via an
# EventSource and receives Server-Sent Events as the job progresses:
#
#   event: progress    data: {"seq": i, "message": "..."}
#   event: generation  data: {scenario telemetry dict}
#   event: done        data: {job result}
#   event: error       data: {"error": "..."}
#
# The interrupt here is the mid-side: this is a real, chunked, live stream on
# top of stdlib http.server — nothing simulated. Swap the job producer for a
# Kafka/Kinesis consumer and the UI barely changes.
# ==========================================================================
def h_sse(job_id: str, handler: "Handler") -> None:
    """Stream job progress and generation events to an EventSource client.

    Returns nothing because the whole response body is written incrementally to
    the socket; the shared request parser skips this handler for that reason.
    """
    ev = lambda name, data: f"event: {name}\ndata: {json.dumps(data, default=_json_default)}\n\n"
    try:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-store, no-transform")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.wfile.write(b": connected\n\n")
        handler.wfile.flush()

        sent_progress, sent_feed = 0, 0
        terminal = False
        last_beat = time.monotonic()
        while not terminal:
            state = STATE.job(job_id)
            if state is None:
                handler.wfile.write(ev("error", {"error": f"unknown job {job_id}"}).encode())
                break
            feed, _ = STATE.job_feed(job_id, sent_feed)
            prog = (state.get("progress") or [])
            for item in feed:
                sent_feed += 1
                handler.wfile.write(ev("generation", item).encode())
            for row in prog[sent_progress:]:
                sent_progress += 1
                handler.wfile.write(ev("progress", {"seq": sent_progress,
                                                    "message": row["message"]}).encode())
            if state["status"] == "complete":
                handler.wfile.write(ev("done", state.get("result") or {}).encode())
                terminal = True
            elif state["status"] == "failed":
                handler.wfile.write(ev("error", {"error": state.get("error"),
                                                 "traceback": state.get("traceback")}).encode())
                terminal = True
            else:
                handler.wfile.flush()
                now = time.monotonic()
                if now - last_beat > 12:                    # keepalive comment
                    handler.wfile.write(b": beat\n\n")
                    last_beat = now
                time.sleep(0.25)
        handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):          # client went away
        pass
    finally:
        handler.close_connection = True


# ==========================================================================
ROUTES_GET: Dict[str, Callable[[Dict, Dict], Tuple[int, Dict]]] = {
    "/api/health": h_health,
    "/api/config": h_config,
    "/api/taxonomy": h_taxonomy,
    "/api/runs": h_runs,
    "/api/gap": h_gap_get,
    "/api/loop/latest": h_loop_latest,
    "/api/models": h_models,
    "/api/experiments": h_experiments,
}

ROUTES_POST: Dict[str, Callable[[Dict, Dict], Tuple[int, Dict]]] = {
    "/api/simulate": h_simulate,
    "/api/redteam/generate": h_redteam_generate,
    "/api/detect": h_detect,
    "/api/score": h_score,
    "/api/attacks": h_attacks,
    "/api/search": h_search,
    "/api/attack": h_attack_detail,
    "/api/gap": h_gap_post,
    "/api/loop": h_loop,
}


class SGServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that treats client disconnects as normal.

    A browser that aborts mid-request (navigation, refresh, timeout) will often
    RST the socket while the server is still reading a request line or writing
    a response. ``ThreadingHTTPServer`` prints a full traceback for every such
    connection; the dashboard generating any aborted request then spams stderr
    with scary-but-harmless errors. Overriding ``handle_error`` keeps those
    quiet (they are not server failures) while real errors still traceback.
    """

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError,
                            ConnectionAbortedError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    server_version = "SovereignGuard/1.0"
    protocol_version = "HTTP/1.1"

    # ---- helpers
    def _send(self, code: int, payload: Dict) -> None:
        body = json.dumps(payload, default=_json_default).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError,
                ConnectionAbortedError, TimeoutError):
            pass                        # client went away mid-response: normal

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        try:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError,
                ConnectionAbortedError, TimeoutError):
            pass                        # client went away mid-response: normal

    def log_message(self, fmt: str, *args) -> None:
        if os.environ.get("SG_HTTP_LOG"):
            super().log_message(fmt, *args)

    # ---- verbs
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        u = urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if path in ROUTES_GET:
                code, payload = ROUTES_GET[path](q, {})
                return self._send(code, payload)
            if path.startswith("/api/taxonomy/"):
                return self._send(*h_taxonomy_one(path.rsplit("/", 1)[-1]))
            if path.startswith("/api/runs/"):
                return self._send(*h_run_one(path.rsplit("/", 1)[-1]))
            if path.startswith("/api/sse/"):
                return h_sse(path.rsplit("/", 1)[-1], self)
            if path.startswith("/api/jobs/"):
                return self._send(*h_job(path.rsplit("/", 1)[-1]))
            if path.startswith("/api/experiments/"):
                return self._send(*h_experiment_one(path.rsplit("/", 1)[-1]))
            if path.startswith("/api/"):
                return self._send(404, {"error": f"no route {path}",
                                        "routes": sorted(ROUTES_GET) + sorted(ROUTES_POST)})
            # ---- static frontend
            rel = "index.html" if path == "/" else path.lstrip("/")
            target = (FRONTEND_DIR / rel).resolve()
            if FRONTEND_DIR.exists() and str(target).startswith(str(FRONTEND_DIR.resolve())) \
                    and target.is_file():
                return self._send_file(target)
            return self._send(404, {"error": "not found", "hint":
                                    "frontend/index.html missing" if path == "/" else path})
        except Exception as exc:                            # pragma: no cover
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}",
                                    "traceback": traceback.format_exc()})

    def do_POST(self) -> None:
        u = urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            body = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(body, dict):
                return self._send(400, {"error": "body must be a JSON object"})
        except json.JSONDecodeError as exc:
            return self._send(400, {"error": f"invalid JSON: {exc}"})
        except (BrokenPipeError, ConnectionResetError,
                ConnectionAbortedError, TimeoutError):
            return                      # client aborted before the body arrived
        try:
            if path in ROUTES_POST:
                code, payload = ROUTES_POST[path]({}, body)
                return self._send(code, payload)
            return self._send(404, {"error": f"no route {path}",
                                    "routes": sorted(ROUTES_POST)})
        except Exception as exc:                            # pragma: no cover
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}",
                                    "traceback": traceback.format_exc()})


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        v = float(o)
        return None if (np.isnan(v) or np.isinf(v)) else v
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    if isinstance(o, pd.DataFrame):
        return o.to_dict("records")
    return str(o)


def _probe_local(host: str, port: int) -> Optional[str]:
    """Ask whatever is listening on host:port what it is. Returns None if it
    does not answer (or is not JSON)."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health",
                                    timeout=1.0) as r:
            body = json.loads(r.read().decode("utf-8"))
        return body.get("service")
    except Exception:
        return None


def serve(host: str = "127.0.0.1", port: int = 8000,
          state: Optional[AppState] = None,
          seed: bool = False) -> ThreadingHTTPServer:
    global STATE
    if state is not None:
        STATE = state
    try:
        httpd = SGServer((host, port), Handler)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        # A raw "Address already in use" traceback helps nobody. Either a
        # SovereignGuard is already serving this port (adopt it, exit 0) or
        # another process holds it (say how to free it, exit 1).
        if _probe_local(host, port) == "sovereignguard":
            print(f"SovereignGuard is already running on http://{host}:{port}/ "
                  f"— nothing to start.")
            print(f"  dashboard : http://{host}:{port}/")
            print(f"  health    : http://{host}:{port}/api/health")
            print("Restart it with:  ss -ltnp | grep :%d  then  kill <pid>, "
                  "then rerun this command." % port)
            raise SystemExit(0)
        print(f"os error: port {port} is already in use by another process "
              "(not SovereignGuard).")
        print(f"  find the holder:  ss -ltnp | grep :{port}")
        print(f"  free the port:    kill <pid>   (or  fuser -k {port}/tcp)")
        print(f"  or serve elsewhere: python sg.py serve --port {port + 1}")
        raise SystemExit(1)
    if seed:
        seeded = STATE.seed_snapshot()
        if seeded:
            print(f"seeded from snapshot: run {seeded['run_id']}, "
                  f"{seeded['n_transactions']:,} transactions, "
                  f"{seeded['n_attack_scenarios']} attack scenarios")
            print(f"  dashboard opens fully populated (default run "
                  f"{STATE.default_run})")
        else:
            print("no snapshot found at data/snapshot/ — dashboard starts "
                  "empty until a simulation is built")
            print(f"  create one with:  python sg.py snapshot "
                  f"(then restart this server)")
    return httpd


def main() -> None:
    host = os.environ.get("SG_HOST", "127.0.0.1")
    port = int(os.environ.get("SG_PORT", "8000"))
    seed = os.environ.get("SG_SEED", "1").lower() not in ("0", "false", "no")
    httpd = serve(host, port, seed=seed)
    print(f"SovereignGuard API + dashboard on http://{host}:{port}")
    print(f"  dashboard : http://{host}:{port}/")
    print(f"  health    : http://{host}:{port}/api/health")
    print("Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
