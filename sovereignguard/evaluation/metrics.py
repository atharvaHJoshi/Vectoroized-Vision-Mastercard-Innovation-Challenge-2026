"""
Evaluation metrics (Phase 13) — implemented directly in numpy.

The guiding rule from the plan: never report accuracy alone. At a 1% fraud base
rate a model that predicts "legitimate" for everything scores 99% accuracy and
is worthless. Everything here is therefore built around the precision/recall
trade-off, the false-positive rate on legitimate traffic, and ranking quality
(ROC-AUC / PR-AUC) which is threshold-independent.

`choose_threshold_at_fpr` implements the operating-point policy: pick the
highest-recall threshold whose false-positive rate on legitimate traffic stays
inside a stated budget. A fraud system is always deployed at a chosen operating
point, so every headline number in this project is reported at one.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Sequence

import numpy as np


# --------------------------------------------------------------------------
def roc_auc(y: np.ndarray, score: np.ndarray) -> float:
    """Rank-based AUC with correct handling of tied scores."""
    y = np.asarray(y).ravel()
    s = np.asarray(score, dtype=np.float64).ravel()
    n_pos = float((y == 1).sum())
    n_neg = float((y == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    s_sorted = s[order]
    # average ranks for ties
    ranks = np.empty(len(s), dtype=np.float64)
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s_sorted[j + 1] == s_sorted[i]:
            j += 1
        ranks[i:j + 1] = 0.5 * (i + j) + 1.0
        i = j + 1
    r = np.empty(len(s), dtype=np.float64)
    r[order] = ranks
    sum_pos = r[y == 1].sum()
    return float((sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def pr_curve(y: np.ndarray, score: np.ndarray):
    """Precision/recall at every distinct threshold, descending by score."""
    y = np.asarray(y).ravel()
    s = np.asarray(score, dtype=np.float64).ravel()
    order = np.argsort(-s, kind="mergesort")
    ys = y[order]
    ss = s[order]
    tp = np.cumsum(ys == 1)
    fp = np.cumsum(ys == 0)
    total_pos = float((y == 1).sum())
    # keep only the last index of each tied run
    distinct = np.r_[np.where(np.diff(ss) != 0)[0], len(ss) - 1]
    tp_d = tp[distinct].astype(np.float64)
    fp_d = fp[distinct].astype(np.float64)
    precision = np.where(tp_d + fp_d > 0, tp_d / np.maximum(tp_d + fp_d, 1e-12), 1.0)
    recall = tp_d / max(total_pos, 1e-12)
    return precision, recall, ss[distinct]


def average_precision(y: np.ndarray, score: np.ndarray) -> float:
    """PR-AUC as the step-wise average precision (no interpolation)."""
    precision, recall, _ = pr_curve(y, score)
    if len(recall) == 0:
        return float("nan")
    prev_r = 0.0
    ap = 0.0
    for p, r in zip(precision, recall):
        ap += (r - prev_r) * p
        prev_r = r
    return float(ap)


def roc_curve_points(y: np.ndarray, score: np.ndarray, max_points: int = 300):
    y = np.asarray(y).ravel()
    s = np.asarray(score, dtype=np.float64).ravel()
    order = np.argsort(-s, kind="mergesort")
    ys = y[order]
    tp = np.cumsum(ys == 1).astype(np.float64)
    fp = np.cumsum(ys == 0).astype(np.float64)
    P = max(float((y == 1).sum()), 1e-12)
    N = max(float((y == 0).sum()), 1e-12)
    tpr = tp / P
    fpr = fp / N
    if len(tpr) > max_points:
        idx = np.unique(np.linspace(0, len(tpr) - 1, max_points).astype(int))
        tpr, fpr = tpr[idx], fpr[idx]
    return (np.r_[0.0, fpr, 1.0].tolist(), np.r_[0.0, tpr, 1.0].tolist())


# --------------------------------------------------------------------------
@dataclass
class Metrics:
    threshold: float
    n: int
    n_positive: int
    n_negative: int
    tp: int
    fp: int
    tn: int
    fn: int
    precision: float
    recall: float
    f1: float
    f2: float
    specificity: float
    fpr: float
    fnr: float
    accuracy: float
    balanced_accuracy: float
    roc_auc: float
    pr_auc: float
    detection_rate: float
    alert_rate: float
    alerts_per_1k_legit: float
    value_detected_share: float = float("nan")
    latency_us_per_txn: float = float("nan")

    def to_dict(self) -> Dict:
        return {k: (None if isinstance(v, float) and np.isnan(v) else v)
                for k, v in asdict(self).items()}

    def headline(self) -> str:
        return (f"recall={self.recall:.4f} precision={self.precision:.4f} "
                f"f1={self.f1:.4f} fpr={self.fpr:.5f} roc_auc={self.roc_auc:.4f}")


def compute_metrics(y: np.ndarray, prob: np.ndarray, threshold: float,
                    amounts: Optional[np.ndarray] = None,
                    latency_us_per_txn: float = float("nan")) -> Metrics:
    y = np.asarray(y).ravel().astype(int)
    p = np.asarray(prob, dtype=np.float64).ravel()
    pred = (p >= threshold).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    n_pos, n_neg = tp + fn, tn + fp
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / n_pos if n_pos else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    f2 = 5 * prec * rec / (4 * prec + rec) if (4 * prec + rec) else 0.0
    spec = tn / n_neg if n_neg else 0.0
    val_share = float("nan")
    if amounts is not None:
        a = np.asarray(amounts, dtype=np.float64).ravel()
        fraud_val = a[y == 1].sum()
        if fraud_val > 0:
            val_share = float(a[(y == 1) & (pred == 1)].sum() / fraud_val)
    return Metrics(
        threshold=float(threshold), n=int(len(y)), n_positive=n_pos, n_negative=n_neg,
        tp=tp, fp=fp, tn=tn, fn=fn,
        precision=float(prec), recall=float(rec), f1=float(f1), f2=float(f2),
        specificity=float(spec),
        fpr=float(fp / n_neg) if n_neg else 0.0,
        fnr=float(fn / n_pos) if n_pos else 0.0,
        accuracy=float((tp + tn) / len(y)) if len(y) else 0.0,
        balanced_accuracy=float(0.5 * (rec + spec)),
        roc_auc=roc_auc(y, p), pr_auc=average_precision(y, p),
        detection_rate=float(rec),
        alert_rate=float((tp + fp) / len(y)) if len(y) else 0.0,
        alerts_per_1k_legit=float(1000.0 * fp / n_neg) if n_neg else 0.0,
        value_detected_share=val_share,
        latency_us_per_txn=float(latency_us_per_txn),
    )


# --------------------------------------------------------------------------
def choose_threshold_at_fpr(y: np.ndarray, prob: np.ndarray,
                            max_fpr: float) -> float:
    """Highest-recall threshold whose FPR on legitimate traffic <= max_fpr.

    This is the operating-point policy for the whole project: the false-positive
    budget is fixed first (it is a business constraint), then recall is
    maximised inside it. Comparing models at a common FPR budget is the only
    way a recall improvement means anything.
    """
    y = np.asarray(y).ravel()
    p = np.asarray(prob, dtype=np.float64).ravel()
    neg = p[y == 0]
    if neg.size == 0:
        return 0.5
    # (1 - max_fpr) quantile of legitimate scores
    q = float(np.quantile(neg, 1.0 - max_fpr, method="higher"))
    # nudge above ties so the realised FPR does not overshoot the budget
    above = neg[neg > q]
    thr = float(np.nextafter(q, np.inf)) if above.size == 0 else float(min(q + 1e-12, above.min()))
    return float(np.clip(thr, 1e-9, 1.0 - 1e-9))


def choose_threshold_max_f1(y: np.ndarray, prob: np.ndarray) -> float:
    precision, recall, thresholds = pr_curve(y, prob)
    f1 = np.where(precision + recall > 0, 2 * precision * recall /
                  np.maximum(precision + recall, 1e-12), 0.0)
    return float(thresholds[int(np.argmax(f1))])


def operating_curve(y: np.ndarray, prob: np.ndarray,
                    fpr_budgets: Sequence[float] = (0.001, 0.002, 0.005, 0.01, 0.02, 0.05)
                    ) -> List[Dict]:
    """Recall achievable at a range of false-positive budgets."""
    out = []
    for b in fpr_budgets:
        thr = choose_threshold_at_fpr(y, prob, b)
        m = compute_metrics(y, prob, thr)
        out.append({"fpr_budget": b, "threshold": thr, "realised_fpr": m.fpr,
                    "recall": m.recall, "precision": m.precision, "f1": m.f1,
                    "alerts_per_1k_legit": m.alerts_per_1k_legit})
    return out


def per_group_metrics(y: np.ndarray, prob: np.ndarray, groups: np.ndarray,
                      threshold: float, min_count: int = 1) -> List[Dict]:
    """Recall broken out by a categorical column (attack type, difficulty...).

    Only defined for positives, so this reports recall/detected/missed rather
    than precision — precision is not attributable to an attack type.
    """
    y = np.asarray(y).ravel()
    p = np.asarray(prob, dtype=np.float64).ravel()
    g = np.asarray(groups).ravel()
    pred = (p >= threshold).astype(int)
    rows = []
    for key in sorted(set(g[y == 1].tolist())):
        m = (g == key) & (y == 1)
        cnt = int(m.sum())
        if cnt < min_count:
            continue
        det = int((pred[m] == 1).sum())
        rows.append({"group": str(key), "n": cnt, "detected": det,
                     "missed": cnt - det,
                     "recall": float(det / cnt) if cnt else 0.0,
                     "mean_score": float(p[m].mean())})
    return sorted(rows, key=lambda r: r["recall"])


def compare_models(results: Dict[str, Metrics]) -> List[Dict]:
    rows = []
    for name, m in results.items():
        d = m.to_dict()
        d["model"] = name
        rows.append(d)
    return sorted(rows, key=lambda r: -(r.get("f1") or 0))


def bootstrap_ci(y: np.ndarray, prob: np.ndarray, threshold: float,
                 metric: str = "recall", n_boot: int = 200,
                 seed: int = 0, alpha: float = 0.05) -> Dict[str, float]:
    """Percentile bootstrap CI so reported deltas can be judged against noise."""
    y = np.asarray(y).ravel()
    p = np.asarray(prob, dtype=np.float64).ravel()
    rng = np.random.default_rng(seed)
    n = len(y)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        m = compute_metrics(y[idx], p[idx], threshold)
        vals.append(getattr(m, metric))
    v = np.asarray(vals, dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"point": float("nan"), "lo": float("nan"), "hi": float("nan")}
    point = getattr(compute_metrics(y, p, threshold), metric)
    return {"point": float(point),
            "lo": float(np.quantile(v, alpha / 2)),
            "hi": float(np.quantile(v, 1 - alpha / 2)),
            "n_boot": int(n_boot)}
