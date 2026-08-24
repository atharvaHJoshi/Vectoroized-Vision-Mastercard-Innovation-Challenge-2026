"""
Blue Team detector: splitting, training, scoring, explaining (Phases 12-14, 19).

SPLITTING (Phase 14)
--------------------
Splits are *temporal and grouped*, not random. Two rules:

  1. Time-ordered. Train on the earliest window, validate on the next, test on
     the last. Randomly shuffling a payment stream lets the model see a
     customer's future when predicting their past, which inflates every metric.

  2. Attack-campaign grouped. All events of one attack_id land in the same
     split. An account-takeover produces 8-12 correlated rows; splitting them
     across train and test leaks the answer.

`unseen_attack_split` additionally holds out entire attack *families* so the
question "can this detect fraud it has never seen?" can actually be asked.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import config as C
from .evaluation.metrics import (Metrics, choose_threshold_at_fpr, compute_metrics,
                                 operating_curve, per_group_metrics)
from .features import assert_no_leakage
from .ml import GradientBoostingClassifier, RandomForestClassifier
from .ml.models import BaseModel
from .risk import RiskEngine
from .schema import FEATURE_COLUMNS, FEATURE_LABELS


# ==========================================================================
# Splitting
# ==========================================================================
@dataclass
class Split:
    train: np.ndarray
    valid: np.ndarray
    test: np.ndarray
    meta: Dict = field(default_factory=dict)

    def sizes(self) -> Dict[str, int]:
        return {"train": int(len(self.train)), "valid": int(len(self.valid)),
                "test": int(len(self.test))}


def temporal_grouped_split(tx: pd.DataFrame, frac_train: float = 0.6,
                           frac_valid: float = 0.15) -> Split:
    """Time-ordered split with attack campaigns kept intact.

    Rows are ordered by time; cut points are taken on the time axis. Any attack
    that straddles a boundary is assigned wholly to the split containing the
    majority of its events, so no campaign appears in two splits.
    """
    if "timestamp" not in tx:
        raise ValueError("tx must contain 'timestamp'")
    n = len(tx)
    ts = tx["timestamp"].to_numpy()
    order = np.argsort(ts, kind="mergesort")
    t_sorted = ts[order]
    i_tr = int(n * frac_train)
    i_va = int(n * (frac_train + frac_valid))
    t_tr = t_sorted[min(i_tr, n - 1)]
    t_va = t_sorted[min(i_va, n - 1)]

    bucket = np.where(ts <= t_tr, 0, np.where(ts <= t_va, 1, 2))

    # Reassign whole attack campaigns by majority bucket.
    aid = tx["attack_id"].to_numpy() if "attack_id" in tx else np.array([""] * n)
    has_aid = aid != ""
    if has_aid.any():
        df = pd.DataFrame({"aid": aid[has_aid], "b": bucket[has_aid]})
        maj = df.groupby("aid")["b"].agg(lambda s: int(s.value_counts().idxmax()))
        mapped = df["aid"].map(maj).to_numpy()
        bucket[has_aid] = mapped

    return Split(
        train=np.where(bucket == 0)[0],
        valid=np.where(bucket == 1)[0],
        test=np.where(bucket == 2)[0],
        meta={"kind": "temporal_grouped", "t_train_end": int(t_tr),
              "t_valid_end": int(t_va), "frac_train": frac_train,
              "frac_valid": frac_valid},
    )


def unseen_attack_split(tx: pd.DataFrame, holdout_types: Sequence[str],
                        frac_train: float = 0.7) -> Split:
    """Train on some attack families, test on entirely unseen ones (Exp 3).

    Legitimate traffic is split by time as usual. Held-out attack families never
    appear in train or valid; they appear only in test.

    The test window ALSO retains the seen families that fall after the time cut.
    That is deliberate: without them there is no same-threshold reference to
    compare unseen-family recall against, and a bare "recall on unseen families"
    number is uninterpretable — you cannot tell whether a low value means poor
    transfer or simply a hard evaluation window.
    """
    holdout = set(holdout_types)
    atype = tx["attack_type"].to_numpy()
    y = tx["fraud_label"].to_numpy()
    ts = tx["timestamp"].to_numpy()

    is_held = np.isin(atype, list(holdout)) & (y == 1)
    legit = y == 0
    seen_attack = (y == 1) & ~is_held

    if legit.any():
        t_cut = float(np.quantile(ts[legit], frac_train))
        t_val = float(np.quantile(ts[legit], frac_train * 0.85))
    else:
        t_cut = float(np.median(ts))
        t_val = float(np.quantile(ts, 0.6))

    early = ts <= t_cut
    valid_mask = (legit | seen_attack) & early & (ts > t_val)
    train_mask = (legit | seen_attack) & early & ~valid_mask
    # test: late legitimate traffic + late seen attacks + ALL held-out attacks
    test_mask = ((legit | seen_attack) & ~early) | is_held

    return Split(
        train=np.where(train_mask)[0],
        valid=np.where(valid_mask)[0],
        test=np.where(test_mask)[0],
        meta={"kind": "unseen_attack", "holdout_types": sorted(holdout),
              "t_cut": int(t_cut), "n_holdout_events": int(is_held.sum())},
    )


# ==========================================================================
# Detector
# ==========================================================================
MODEL_REGISTRY = {
    "gbdt": GradientBoostingClassifier,
    "forest": RandomForestClassifier,
}


def optional_backends() -> Dict[str, bool]:
    """Report which third-party backends are importable in this environment.

    The project runs fully without them. When present, `train_detector` can be
    asked for them so results can be cross-checked against reference libraries.
    """
    out = {}
    for name, mod in (("xgboost", "xgboost"), ("lightgbm", "lightgbm"),
                      ("sklearn", "sklearn"), ("shap", "shap")):
        try:
            __import__(mod)
            out[name] = True
        except Exception:
            out[name] = False
    return out


@dataclass
class Detector:
    """A trained Blue Team model plus everything needed to deploy it."""
    model: BaseModel
    feature_names: List[str]
    threshold: float
    target_fpr: float
    risk: RiskEngine
    metrics: Dict[str, Dict] = field(default_factory=dict)
    train_meta: Dict = field(default_factory=dict)

    # ---------------------------------------------------------------- score
    def predict_proba(self, Xf: pd.DataFrame | np.ndarray) -> np.ndarray:
        X = self._as_matrix(Xf)
        return self.model.predict_proba(X)

    def _as_matrix(self, Xf) -> np.ndarray:
        if isinstance(Xf, pd.DataFrame):
            missing = [c for c in self.feature_names if c not in Xf.columns]
            if missing:
                raise ValueError(f"missing features: {missing[:6]}")
            return Xf[self.feature_names].to_numpy(dtype=np.float32)
        X = np.asarray(Xf, dtype=np.float32)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        return X

    def decide(self, Xf) -> pd.DataFrame:
        p = self.predict_proba(Xf)
        d = self.risk.decide_batch(p)
        return pd.DataFrame({"fraud_probability": p, "risk_score": d["risk_score"],
                             "risk_band": d["band"], "action": d["action"],
                             "flagged": (p >= self.threshold).astype(int)})

    def evaluate(self, Xf, y, amounts=None, groups: Optional[Dict[str, np.ndarray]] = None
                 ) -> Dict:
        X = self._as_matrix(Xf)
        t0 = time.perf_counter()
        p = self.model.predict_proba(X)
        elapsed_us = (time.perf_counter() - t0) * 1e6
        m = compute_metrics(y, p, self.threshold, amounts=amounts,
                            latency_us_per_txn=elapsed_us / max(1, len(X)))
        out = {"overall": m.to_dict(),
               "operating_curve": operating_curve(y, p),
               "risk_distribution": self.risk.distribution(p, y),
               "friction": self.risk.friction_summary(p, y)}
        for name, g in (groups or {}).items():
            out[f"by_{name}"] = per_group_metrics(y, p, g, self.threshold)
        return out

    # ---------------------------------------------------------------- explain
    def explain(self, Xf, top_k: int = 6, max_rows: int = 200) -> List[Dict]:
        """Per-transaction reason codes from SHAP values.

        Returns human-readable contributing factors, ordered by contribution to
        the risk decision. Only positive (risk-increasing) contributions are
        surfaced as reasons, with protective factors reported separately.
        """
        from .ml.treeshap import shap_values
        X = self._as_matrix(Xf)
        if len(X) > max_rows:
            X = X[:max_rows]
        phi, base = shap_values(self.model, X, check=False)
        p = self.model.predict_proba(X)
        dec = self.risk.decide_batch(p)
        names = self.feature_names
        rows = []
        for i in range(len(X)):
            contrib = phi[i]
            order = np.argsort(-np.abs(contrib))
            reasons, protective = [], []
            for j in order[: top_k * 3]:
                if abs(contrib[j]) < 1e-6:
                    continue
                item = {
                    "feature": names[j],
                    "label": FEATURE_LABELS.get(names[j], names[j]),
                    "value": float(X[i, j]),
                    "contribution": round(float(contrib[j]), 5),
                }
                if contrib[j] > 0 and len(reasons) < top_k:
                    reasons.append(item)
                elif contrib[j] < 0 and len(protective) < 3:
                    protective.append(item)
            rows.append({
                "fraud_probability": float(p[i]),
                "risk_score": float(dec["risk_score"][i]),
                "risk_band": str(dec["band"][i]),
                "action": str(dec["action"][i]),
                "base_value": round(float(base), 5),
                "reasons": reasons,
                "protective_factors": protective,
            })
        return rows

    def narrative(self, one_explanation: Dict) -> str:
        """Analyst-facing sentence form of an explanation."""
        e = one_explanation
        head = (f"{e['risk_band']} risk ({e['risk_score']:.1f}/100) -> {e['action']}. "
                f"Model probability {e['fraud_probability']:.3f}.")
        if not e["reasons"]:
            return head + " No individually material risk contributors."
        bullets = "; ".join(f"{r['label']} = {r['value']:.4g}" for r in e["reasons"])
        return head + " Principal drivers: " + bullets + "."

    # ---------------------------------------------------------------- io
    def save(self, directory) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.model.save(directory / "model.json.gz")
        meta = {"feature_names": self.feature_names, "threshold": self.threshold,
                "target_fpr": self.target_fpr, "risk": self.risk.to_dict(),
                "metrics": self.metrics, "train_meta": self.train_meta,
                "model_kind": self.model.kind}
        (directory / "detector.json").write_text(json.dumps(meta, indent=2, default=str))
        return directory

    @staticmethod
    def load(directory) -> "Detector":
        directory = Path(directory)
        meta = json.loads((directory / "detector.json").read_text())
        model = BaseModel.load(directory / "model.json.gz")
        return Detector(
            model=model, feature_names=list(meta["feature_names"]),
            threshold=float(meta["threshold"]), target_fpr=float(meta["target_fpr"]),
            risk=RiskEngine(operating_threshold=float(meta["threshold"])),
            metrics=meta.get("metrics", {}), train_meta=meta.get("train_meta", {}))


# ==========================================================================
def train_detector(
    feats: pd.DataFrame,
    tx: pd.DataFrame,
    split: Split,
    model_kind: str = "gbdt",
    target_fpr: float = C.TARGET_FPR_BUDGET,
    model_params: Optional[Dict] = None,
    seed: int = C.SEED,
    verbose: bool = False,
) -> Detector:
    """Fit a model, choose the operating point on VALIDATION, never on test."""
    assert_no_leakage(feats)
    if model_kind not in MODEL_REGISTRY:
        raise ValueError(f"unknown model_kind {model_kind!r}; "
                         f"choose from {sorted(MODEL_REGISTRY)}")

    X = feats[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    y = tx["fraud_label"].to_numpy().astype(np.float64)

    itr, iva = split.train, split.valid
    if len(itr) == 0:
        raise ValueError("empty training split")
    if len(iva) == 0:                      # fall back to a tail slice of train
        cut = int(len(itr) * 0.85)
        iva, itr = itr[cut:], itr[:cut]

    pos = float(y[itr].sum())
    neg = float(len(itr) - pos)
    if pos == 0:
        raise ValueError("training split contains no fraud")

    defaults: Dict[str, Dict] = {
        "gbdt": dict(n_estimators=300, learning_rate=0.10, max_depth=6,
                     max_leaves=63, min_samples_leaf=25, l2=1.0,
                     subsample=0.8, colsample=0.7, max_bins=64,
                     early_stopping_rounds=30,
                     scale_pos_weight=float(np.clip(neg / max(pos, 1.0), 1.0, 40.0)),
                     random_state=seed, verbose=verbose),
        "forest": dict(n_estimators=120, max_depth=14, min_samples_leaf=5,
                       colsample=0.35, bootstrap=True, max_bins=64,
                       class_weight_balanced=True, random_state=seed,
                       verbose=verbose),
    }
    params = {**defaults[model_kind], **(model_params or {})}
    model = MODEL_REGISTRY[model_kind](**params)

    t0 = time.perf_counter()
    if model_kind == "gbdt":
        model.fit(X[itr], y[itr], eval_set=(X[iva], y[iva]),
                  feature_names=FEATURE_COLUMNS)
    else:
        model.fit(X[itr], y[itr], feature_names=FEATURE_COLUMNS)
    fit_s = time.perf_counter() - t0

    # Operating point from VALIDATION only.
    p_va = model.predict_proba(X[iva])
    thr = choose_threshold_at_fpr(y[iva], p_va, target_fpr)

    det = Detector(
        model=model, feature_names=list(FEATURE_COLUMNS), threshold=float(thr),
        target_fpr=float(target_fpr), risk=RiskEngine(operating_threshold=float(thr)),
        train_meta={
            "model_kind": model_kind, "params": params, "fit_seconds": round(fit_s, 2),
            "split": split.sizes(), "split_meta": split.meta,
            "train_fraud_rate": float(y[itr].mean()),
            "n_features": len(FEATURE_COLUMNS),
            "n_trees": len(model.trees_),
            "best_iteration": getattr(model, "best_iteration_", len(model.trees_)),
            "seed": seed,
        },
    )
    det.metrics["validation"] = compute_metrics(y[iva], p_va, thr).to_dict()
    if len(split.test):
        ite = split.test
        groups = {}
        if "attack_type" in tx:
            groups["attack_type"] = tx["attack_type"].to_numpy()[ite]
        if "difficulty" in tx:
            groups["difficulty"] = tx["difficulty"].to_numpy()[ite]
        det.metrics["test"] = det.evaluate(
            feats.iloc[ite], y[ite],
            amounts=tx["amount"].to_numpy()[ite], groups=groups)
    det.metrics["top_features"] = [
        {"feature": f, "label": FEATURE_LABELS.get(f, f), "importance": round(v, 5)}
        for f, v in model.importance_table(20)]
    return det
