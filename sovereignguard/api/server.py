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
  GET  /api/gap                        latest gap analysis
  POST /api/gap                        recompute gap analysis for a model run
  POST /api/loop                       run the adaptive loop        (async job)
  GET  /api/loop/latest                latest loop result (hero screen)
  GET  /api/models                     model runs + metrics
  GET  /api/experiments                experiment results
  GET  /api/experiments/{id}           one experiment
  GET  /api/jobs/{job_id}              async job status/result
  GET  /                               dashboard (static frontend)
"""
from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
import traceback
import uuid
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

    # ---- jobs
    def start_job(self, kind: str, fn: Callable[[Callable[[str], None]], Dict]) -> str:
        job_id = f"job_{uuid.uuid4().hex[:10]}"
        with self.lock:
            self.jobs[job_id] = {"job_id": job_id, "kind": kind, "status": "running",
                                 "created_at": time.time(), "progress": [],
                                 "result": None, "error": None}

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
            if key and key in self.detectors:
                return self.detectors[key]
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
        return 404, {"error": f"unknown run {run_id}"}
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

    def work(note) -> Dict:
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        cfg = {"scale": scale, "seed": seed, "target_prevalence": prevalence,
               "attack_types": attack_types, "difficulty_mix": difficulty_mix,
               "model_kind": model_kind}
        STATE.store.create_run(run_id, "simulate", cfg, scale, seed)
        note(f"building world at scale={scale}")
        world = build_world(scale, seed, target_prevalence=prevalence,
                            attack_types=attack_types,
                            difficulty_mix=difficulty_mix, quiet=True)
        STATE.put_world(run_id, world)
        note(f"world ready: {len(world.tx):,} transactions, "
             f"prevalence {world.y.mean():.4%}")
        out = {"run_id": run_id, "summary": world.summary()}

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
        note("done")
        return out

    return 202, {"job_id": STATE.start_job("simulate", work), "status": "running"}


def h_redteam_generate(_q: Dict, body: Dict) -> Tuple[int, Dict]:
    """Generate attacks against an existing world (Red Team simulator page)."""
    world = STATE.get_world(body.get("run_id"))
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

    batch = world.red_team.generate(n, attack_types=atypes, difficulty_mix=mix,
                                   stream=f"api:{uuid.uuid4().hex[:6]}")
    scen = batch.scenarios
    return 200, {
        "n_scenarios": batch.n_scenarios,
        "n_events": batch.n_events,
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


def h_detect(_q: Dict, body: Dict) -> Tuple[int, Dict]:
    """Run the Blue Team over a run's test window and return full metrics."""
    world = STATE.get_world(body.get("run_id"))
    det = STATE.get_detector(body.get("detector_key"))
    if world is None or det is None:
        return 400, {"error": "need a loaded world and detector; POST /api/simulate"}
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
    return 200, {
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


def h_score(_q: Dict, body: Dict) -> Tuple[int, Dict]:
    """Score one transaction from a run and explain the decision."""
    world = STATE.get_world(body.get("run_id"))
    det = STATE.get_detector(body.get("detector_key"))
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
                                  "fraud_label", "attack_type", "attack_stage",
                                  "difficulty")},
        "decision": {k: expl[k] for k in ("fraud_probability", "risk_score",
                                          "risk_band", "action")},
        "explanation": expl,
        "narrative": det.narrative(expl),
        "is_correct": bool((expl["fraud_probability"] >= det.threshold) ==
                           bool(txr["fraud_label"])),
    }


def h_gap_get(_q: Dict, _b: Dict) -> Tuple[int, Dict]:
    rec = STATE.store.latest_gap()
    if not rec:
        return 404, {"error": "no gap analysis yet; run /api/simulate"}
    return 200, rec


def h_gap_post(_q: Dict, body: Dict) -> Tuple[int, Dict]:
    world = STATE.get_world(body.get("run_id"))
    det = STATE.get_detector(body.get("detector_key"))
    if world is None or det is None:
        return 400, {"error": "need a loaded world and detector"}
    split = temporal_grouped_split(world.tx)
    gap, _ = diagnose(world, det, split, on=str(body.get("on", "test")))
    gid = f"gap_{uuid.uuid4().hex[:8]}"
    STATE.store.save_gap(gid, body.get("model_run_id", "adhoc"), gap.to_dict())
    return 200, {"gap_id": gid, "headline": gap.headline(), **gap.to_dict()}


def h_loop(_q: Dict, body: Dict) -> Tuple[int, Dict]:
    """The hero action: diagnose, adapt, retrain, retest (async)."""
    world = STATE.get_world(body.get("run_id"))
    det = STATE.get_detector(body.get("detector_key"))
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
    "/api/gap": h_gap_post,
    "/api/loop": h_loop,
}


class Handler(BaseHTTPRequestHandler):
    server_version = "SovereignGuard/1.0"
    protocol_version = "HTTP/1.1"

    # ---- helpers
    def _send(self, code: int, payload: Dict) -> None:
        body = json.dumps(payload, default=_json_default).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

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


def serve(host: str = "127.0.0.1", port: int = 8000,
          state: Optional[AppState] = None) -> ThreadingHTTPServer:
    global STATE
    if state is not None:
        STATE = state
    httpd = ThreadingHTTPServer((host, port), Handler)
    return httpd


def main() -> None:
    host = os.environ.get("SG_HOST", "127.0.0.1")
    port = int(os.environ.get("SG_PORT", "8000"))
    httpd = serve(host, port)
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
