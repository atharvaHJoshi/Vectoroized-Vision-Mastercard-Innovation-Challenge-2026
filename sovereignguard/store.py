"""
Persistence layer (Phase 22).

SQLite by default so the project runs with zero setup; the schema is plain SQL
with no SQLite-specific types, and `postgres_ddl()` emits the equivalent
PostgreSQL DDL for the deployment described in the plan. Switching engines means
swapping the connection, not rewriting the queries.

Tables mirror the plan: customers, merchants, devices, transactions,
attack_scenarios, attack_results, model_runs, risk_scores, gap_analysis.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    created_at    REAL NOT NULL,
    kind          TEXT NOT NULL,
    scale         TEXT,
    seed          INTEGER,
    status        TEXT NOT NULL,
    config_json   TEXT,
    summary_json  TEXT
);

CREATE TABLE IF NOT EXISTS customers (
    run_id TEXT, customer_id TEXT, persona TEXT, age INTEGER,
    home_city TEXT, account_age_days INTEGER, median_amount REAL,
    kyc_level TEXT, credit_limit REAL, is_synthetic_identity INTEGER,
    PRIMARY KEY (run_id, customer_id)
);

CREATE TABLE IF NOT EXISTS merchants (
    run_id TEXT, merchant_id TEXT, category TEXT, merchant_size TEXT,
    merchant_age_days INTEGER, city TEXT, median_ticket REAL,
    intrinsic_risk REAL, chargeback_rate REAL, is_fraud_merchant INTEGER,
    PRIMARY KEY (run_id, merchant_id)
);

CREATE TABLE IF NOT EXISTS devices (
    run_id TEXT, device_id TEXT, owner_customer_id TEXT, os_family TEXT,
    is_emulator INTEGER, is_rooted INTEGER, reputation REAL,
    PRIMARY KEY (run_id, device_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    run_id TEXT, transaction_id TEXT, customer_id TEXT, merchant_id TEXT,
    timestamp INTEGER, amount REAL, payment_method TEXT, channel TEXT,
    transaction_type TEXT, device_id TEXT, city TEXT, auth_result TEXT,
    fraud_label INTEGER, attack_type TEXT, attack_id TEXT,
    attack_stage TEXT, difficulty TEXT,
    PRIMARY KEY (run_id, transaction_id)
);
CREATE INDEX IF NOT EXISTS ix_txn_run_time ON transactions(run_id, timestamp);
CREATE INDEX IF NOT EXISTS ix_txn_attack ON transactions(run_id, attack_id);

CREATE TABLE IF NOT EXISTS attack_scenarios (
    run_id TEXT, attack_id TEXT, attack_type TEXT, difficulty TEXT,
    victim_customer_id TEXT, persona TEXT, n_events INTEGER,
    total_value REAL, max_event_value REAL, span_seconds INTEGER,
    stages TEXT, severity TEXT, campaign_id TEXT,
    PRIMARY KEY (run_id, attack_id)
);

CREATE TABLE IF NOT EXISTS model_runs (
    model_run_id TEXT PRIMARY KEY, run_id TEXT, created_at REAL,
    model_kind TEXT, label TEXT, threshold REAL, target_fpr REAL,
    n_trees INTEGER, fit_seconds REAL,
    metrics_json TEXT, params_json TEXT, top_features_json TEXT
);

CREATE TABLE IF NOT EXISTS attack_results (
    model_run_id TEXT, attack_id TEXT, max_score REAL, mean_score REAL,
    n_events INTEGER, detected INTEGER,
    PRIMARY KEY (model_run_id, attack_id)
);

CREATE TABLE IF NOT EXISTS risk_scores (
    model_run_id TEXT, transaction_id TEXT, fraud_probability REAL,
    risk_score REAL, risk_band TEXT, action TEXT, flagged INTEGER,
    fraud_label INTEGER,
    PRIMARY KEY (model_run_id, transaction_id)
);

CREATE TABLE IF NOT EXISTS gap_analysis (
    gap_id TEXT PRIMARY KEY, model_run_id TEXT, created_at REAL,
    n_attacks INTEGER, n_detected INTEGER, n_missed INTEGER, recall REAL,
    report_json TEXT
);

CREATE TABLE IF NOT EXISTS loop_results (
    loop_id TEXT PRIMARY KEY, run_id TEXT, created_at REAL,
    recall_before REAL, recall_after REAL, recall_delta REAL,
    f1_before REAL, f1_after REAL, result_json TEXT
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY, name TEXT, created_at REAL,
    status TEXT, result_json TEXT
);
"""


class Store:
    """Thin persistence wrapper. Safe to use from multiple threads.

    Falls back to a temporary directory if the configured path lives on a
    filesystem without POSIX locking (network mounts, some container bind
    mounts, cloud-synced folders). SQLite raises "disk I/O error" on those, and
    a hard failure at import time would make the whole tool unusable for a
    reason that has nothing to do with the analysis.
    """

    def __init__(self, path: Optional[Path] = None, allow_fallback: bool = True):
        self.path = Path(path or C.DB_PATH)
        self.fallback_used = False
        try:
            self._init_schema()
        except (sqlite3.Error, OSError) as exc:
            # Two distinct failure modes, both must fall back:
            #   OSError        — the directory cannot be created at all
            #   sqlite3.Error  — the directory exists but the filesystem lacks
            #                    the POSIX locking SQLite needs
            if not allow_fallback:
                raise
            import tempfile
            alt = Path(tempfile.gettempdir()) / "sovereignguard" / "sovereignguard.db"
            alt.parent.mkdir(parents=True, exist_ok=True)
            self.path = alt
            self.fallback_used = True
            self._init_schema()
            print(f"[sovereignguard] WARNING: database could not be opened at its "
                  f"configured location ({type(exc).__name__}: {exc}). Falling back "
                  f"to {alt}. Set SG_DB_PATH to a local filesystem to silence this.")

    def _init_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(str(self.path), timeout=30.0,
                              check_same_thread=False)
        con.row_factory = sqlite3.Row
        try:
            try:
                con.execute("PRAGMA journal_mode=WAL")
                con.execute("PRAGMA synchronous=NORMAL")
            except sqlite3.OperationalError:
                pass          # filesystem without WAL support; default journal is fine
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    # ------------------------------------------------------------------ runs
    def create_run(self, run_id: str, kind: str, config: Dict,
                   scale: str = "", seed: int = 0) -> str:
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO runs (run_id, created_at, kind, scale, seed,"
                " status, config_json, summary_json) VALUES (?,?,?,?,?,?,?,?)",
                (run_id, time.time(), kind, scale, int(seed), "running",
                 json.dumps(config, default=str), None))
        return run_id

    def finish_run(self, run_id: str, summary: Dict, status: str = "complete") -> None:
        with self.connect() as con:
            con.execute("UPDATE runs SET status=?, summary_json=? WHERE run_id=?",
                        (status, json.dumps(summary, default=str), run_id))

    def get_run(self, run_id: str) -> Optional[Dict]:
        with self.connect() as con:
            r = con.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        for k in ("config_json", "summary_json"):
            d[k.replace("_json", "")] = json.loads(d.pop(k)) if d.get(k) else None
        return d

    def list_runs(self, limit: int = 50) -> List[Dict]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT run_id, created_at, kind, scale, seed, status, summary_json"
                " FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["summary"] = json.loads(d.pop("summary_json")) if d.get("summary_json") else None
            out.append(d)
        return out

    # ------------------------------------------------------------------ world
    def clear_simulations(self) -> None:
        """Remove every prior simulation's data so the database holds only the
        next simulation written after this call. Experiment records are kept."""
        tables = ["runs", "customers", "merchants", "devices", "transactions",
                  "attack_scenarios", "model_runs", "attack_results",
                  "risk_scores", "gap_analysis", "loop_results"]
        with self.connect() as con:
            for name in tables:
                con.execute(f"DELETE FROM {name}")

    def save_world(self, run_id: str, world) -> None:
        cu = world.customers[["customer_id", "persona", "age", "home_city",
                              "account_age_days", "median_amount", "kyc_level",
                              "credit_limit", "is_synthetic_identity"]].copy()
        me = world.merchants[["merchant_id", "category", "merchant_size",
                              "merchant_age_days", "city", "median_ticket",
                              "intrinsic_risk", "chargeback_rate",
                              "is_fraud_merchant"]].copy()
        dv = world.devices[["device_id", "owner_customer_id", "os_family",
                            "is_emulator", "is_rooted", "reputation"]].copy()
        tx = world.tx[["transaction_id", "customer_id", "merchant_id", "timestamp",
                       "amount", "payment_method", "channel", "transaction_type",
                       "device_id", "city", "auth_result", "fraud_label",
                       "attack_type", "attack_id", "attack_stage", "difficulty"]].copy()
        for df in (cu, me, dv, tx):
            df.insert(0, "run_id", run_id)
        with self.connect() as con:
            for name, df in (("customers", cu), ("merchants", me),
                             ("devices", dv), ("transactions", tx)):
                con.execute(f"DELETE FROM {name} WHERE run_id=?", (run_id,))
                df.to_sql(name, con, if_exists="append", index=False)
            if not world.batch.scenarios.empty:
                sc = world.batch.scenarios.copy()
                sc.insert(0, "run_id", run_id)
                con.execute("DELETE FROM attack_scenarios WHERE run_id=?", (run_id,))
                sc.to_sql("attack_scenarios", con, if_exists="append", index=False)

    # ------------------------------------------------------------------ models
    def save_model_run(self, model_run_id: str, run_id: str, det, label: str = "") -> str:
        tm = det.train_meta
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO model_runs (model_run_id, run_id, created_at,"
                " model_kind, label, threshold, target_fpr, n_trees, fit_seconds,"
                " metrics_json, params_json, top_features_json)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (model_run_id, run_id, time.time(), tm.get("model_kind", ""), label,
                 float(det.threshold), float(det.target_fpr),
                 int(tm.get("n_trees", 0)), float(tm.get("fit_seconds", 0.0)),
                 json.dumps(det.metrics, default=str),
                 json.dumps(tm.get("params", {}), default=str),
                 json.dumps(det.metrics.get("top_features", []), default=str)))
        return model_run_id

    def list_model_runs(self, run_id: Optional[str] = None, limit: int = 50) -> List[Dict]:
        q = ("SELECT model_run_id, run_id, created_at, model_kind, label, threshold,"
             " target_fpr, n_trees, fit_seconds, metrics_json FROM model_runs")
        args: tuple = ()
        if run_id:
            q += " WHERE run_id=?"
            args = (run_id,)
        q += " ORDER BY created_at DESC LIMIT ?"
        args = args + (limit,)
        with self.connect() as con:
            rows = con.execute(q, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["metrics"] = json.loads(d.pop("metrics_json")) if d.get("metrics_json") else {}
            out.append(d)
        return out

    def save_risk_scores(self, model_run_id: str, tx: pd.DataFrame,
                         decisions: pd.DataFrame, limit: int = 50_000) -> None:
        df = pd.DataFrame({
            "model_run_id": model_run_id,
            "transaction_id": tx["transaction_id"].to_numpy()[:limit],
            "fraud_probability": decisions["fraud_probability"].to_numpy()[:limit],
            "risk_score": decisions["risk_score"].to_numpy()[:limit],
            "risk_band": decisions["risk_band"].to_numpy()[:limit],
            "action": decisions["action"].to_numpy()[:limit],
            "flagged": decisions["flagged"].to_numpy()[:limit],
            "fraud_label": tx["fraud_label"].to_numpy()[:limit],
        })
        with self.connect() as con:
            con.execute("DELETE FROM risk_scores WHERE model_run_id=?", (model_run_id,))
            df.to_sql("risk_scores", con, if_exists="append", index=False)

    def save_attack_results(self, model_run_id: str, tx: pd.DataFrame,
                            prob, threshold: float) -> None:
        df = pd.DataFrame({"attack_id": tx["attack_id"].to_numpy(), "p": prob,
                           "y": tx["fraud_label"].to_numpy()})
        df = df[(df["attack_id"] != "") & (df["y"] == 1)]
        if df.empty:
            return
        agg = df.groupby("attack_id")["p"].agg(["max", "mean", "count"]).reset_index()
        agg.columns = ["attack_id", "max_score", "mean_score", "n_events"]
        agg["detected"] = (agg["max_score"] >= threshold).astype(int)
        agg.insert(0, "model_run_id", model_run_id)
        with self.connect() as con:
            con.execute("DELETE FROM attack_results WHERE model_run_id=?", (model_run_id,))
            agg.to_sql("attack_results", con, if_exists="append", index=False)

    def save_gap(self, gap_id: str, model_run_id: str, report: Dict) -> None:
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO gap_analysis (gap_id, model_run_id, created_at,"
                " n_attacks, n_detected, n_missed, recall, report_json)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (gap_id, model_run_id, time.time(), int(report.get("n_attacks", 0)),
                 int(report.get("n_detected", 0)), int(report.get("n_missed", 0)),
                 float(report.get("recall", 0.0)), json.dumps(report, default=str)))

    def latest_gap(self, model_run_id: Optional[str] = None) -> Optional[Dict]:
        q = "SELECT * FROM gap_analysis"
        args: tuple = ()
        if model_run_id:
            q += " WHERE model_run_id=?"
            args = (model_run_id,)
        q += " ORDER BY created_at DESC LIMIT 1"
        with self.connect() as con:
            r = con.execute(q, args).fetchone()
        if not r:
            return None
        d = dict(r)
        d["report"] = json.loads(d.pop("report_json"))
        return d

    def save_loop(self, loop_id: str, run_id: str, res) -> None:
        d = res.to_dict() if hasattr(res, "to_dict") else dict(res)
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO loop_results (loop_id, run_id, created_at,"
                " recall_before, recall_after, recall_delta, f1_before, f1_after,"
                " result_json) VALUES (?,?,?,?,?,?,?,?,?)",
                (loop_id, run_id, time.time(),
                 float(d["before"].get("recall") or 0.0),
                 float(d["after"].get("recall") or 0.0),
                 float(d["delta"].get("recall_delta") or 0.0),
                 float(d["before"].get("f1") or 0.0),
                 float(d["after"].get("f1") or 0.0),
                 json.dumps(d, default=str)))

    def list_loops(self, limit: int = 20) -> List[Dict]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT loop_id, run_id, created_at, recall_before, recall_after,"
                " recall_delta, f1_before, f1_after FROM loop_results"
                " ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def latest_loop(self) -> Optional[Dict]:
        with self.connect() as con:
            r = con.execute("SELECT * FROM loop_results ORDER BY created_at DESC"
                            " LIMIT 1").fetchone()
        if not r:
            return None
        d = dict(r)
        d["result"] = json.loads(d.pop("result_json"))
        return d

    def save_experiment(self, experiment_id: str, name: str, result: Dict,
                        status: str = "complete") -> None:
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO experiments (experiment_id, name, created_at,"
                " status, result_json) VALUES (?,?,?,?,?)",
                (experiment_id, name, time.time(), status,
                 json.dumps(result, default=str)))

    def list_experiments(self) -> List[Dict]:
        with self.connect() as con:
            rows = con.execute("SELECT experiment_id, name, created_at, status"
                               " FROM experiments ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_experiment(self, experiment_id: str) -> Optional[Dict]:
        with self.connect() as con:
            r = con.execute("SELECT * FROM experiments WHERE experiment_id=?",
                            (experiment_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["result"] = json.loads(d.pop("result_json"))
        return d

    # ------------------------------------------------------------------ queries
    def query(self, sql: str, args: Iterable = ()) -> List[Dict]:
        with self.connect() as con:
            rows = con.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]


def postgres_ddl() -> str:
    """PostgreSQL equivalent of SCHEMA, for the deployment in the plan."""
    return (SCHEMA
            .replace("REAL", "DOUBLE PRECISION")
            .replace("INTEGER PRIMARY KEY", "BIGSERIAL PRIMARY KEY")
            .replace("TEXT PRIMARY KEY", "VARCHAR(64) PRIMARY KEY"))
