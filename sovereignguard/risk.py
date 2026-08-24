"""
Risk decision layer (Phase 20).

Converts a fraud probability into a *decision*, because a payment system does
not act on a probability — it allows, monitors, challenges or holds. Thresholds
are prototype policy values in config.RISK_BANDS, tunable per deployment. They
are not, and are not claimed to be, any real scheme's thresholds.

The band boundaries are expressed on a 0-100 risk score. The mapping from model
probability to that score is deliberately *not* the identity: the detector's
operating threshold (chosen at a false-positive budget) is pinned to the
STEP_UP boundary so that the policy bands stay aligned with the model's
calibration instead of drifting whenever the model is retrained.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import numpy as np

from . import config as C


@dataclass
class RiskDecision:
    probability: float
    risk_score: float
    band: str
    action: str
    description: str

    def to_dict(self) -> Dict:
        return asdict(self)


class RiskEngine:
    """Probability -> risk score -> band -> action.

    `operating_threshold` is the probability at which the detector was tuned
    (highest recall inside the FPR budget). It is mapped to the lower edge of
    the STEP_UP band, so a transaction the model would flag is exactly a
    transaction that gets challenged. Below and above that anchor the mapping
    is piecewise-linear in probability.
    """

    def __init__(self, operating_threshold: float = 0.5,
                 bands: Optional[List[C.RiskBand]] = None):
        self.bands = list(bands or C.RISK_BANDS)
        self.operating_threshold = float(np.clip(operating_threshold, 1e-6, 1 - 1e-6))
        self.anchor_score = self._step_up_edge()

    def _step_up_edge(self) -> float:
        for b in self.bands:
            if b.action == "STEP_UP_AUTH":
                return float(b.lower)
        return 60.0

    # ------------------------------------------------------------------
    def score(self, prob) -> np.ndarray:
        """Map probability to a 0-100 risk score, anchored at the threshold."""
        p = np.asarray(prob, dtype=np.float64)
        t = self.operating_threshold
        a = self.anchor_score
        below = (p / t) * a
        above = a + ((p - t) / max(1.0 - t, 1e-9)) * (100.0 - a)
        return np.clip(np.where(p < t, below, above), 0.0, 100.0)

    def band_for(self, risk_score: float) -> C.RiskBand:
        for b in self.bands:
            if b.lower <= risk_score < b.upper:
                return b
        return self.bands[-1]

    def decide(self, prob: float) -> RiskDecision:
        rs = float(self.score(np.array([prob]))[0])
        b = self.band_for(rs)
        return RiskDecision(probability=float(prob), risk_score=round(rs, 2),
                            band=b.name, action=b.action, description=b.description)

    def decide_batch(self, prob) -> Dict[str, np.ndarray]:
        rs = self.score(prob)
        edges = np.array([b.lower for b in self.bands], dtype=np.float64)
        idx = np.clip(np.searchsorted(edges, rs, side="right") - 1, 0, len(self.bands) - 1)
        return {
            "risk_score": rs,
            "band": np.array([self.bands[i].name for i in idx]),
            "action": np.array([self.bands[i].action for i in idx]),
        }

    # ------------------------------------------------------------------
    def distribution(self, prob, y: Optional[np.ndarray] = None) -> List[Dict]:
        """Risk-band distribution, split by true label when available.

        This is the table that shows whether the policy is doing useful work:
        a good operating point puts most fraud in STEP_UP/HOLD and almost all
        legitimate traffic in ALLOW.
        """
        out = self.decide_batch(prob)
        bands = out["band"]
        rows = []
        n = len(bands)
        for b in self.bands:
            m = bands == b.name
            row = {"band": b.name, "action": b.action, "count": int(m.sum()),
                   "share": float(m.sum() / n) if n else 0.0}
            if y is not None:
                yy = np.asarray(y).ravel()
                row["fraud"] = int((yy[m] == 1).sum())
                row["legit"] = int((yy[m] == 0).sum())
                row["fraud_share_of_band"] = (float((yy[m] == 1).mean())
                                              if m.sum() else 0.0)
                tot_fraud = max(int((yy == 1).sum()), 1)
                tot_legit = max(int((yy == 0).sum()), 1)
                row["share_of_all_fraud"] = float((yy[m] == 1).sum() / tot_fraud)
                row["share_of_all_legit"] = float((yy[m] == 0).sum() / tot_legit)
            rows.append(row)
        return rows

    def friction_summary(self, prob, y: Optional[np.ndarray] = None) -> Dict:
        """Customer-friction view: what share of honest traffic gets challenged
        or held, and what share of fraud is stopped versus merely monitored."""
        out = self.decide_batch(prob)
        act = out["action"]
        n = max(len(act), 1)
        challenged = np.isin(act, ["STEP_UP_AUTH", "HOLD_REVIEW"])
        res = {"n": int(len(act)),
               "challenged_share": float(challenged.sum() / n)}
        if y is not None:
            yy = np.asarray(y).ravel()
            legit = yy == 0
            fraud = yy == 1
            res["legit_challenged_share"] = float(challenged[legit].mean()) if legit.any() else 0.0
            res["fraud_stopped_share"] = float(challenged[fraud].mean()) if fraud.any() else 0.0
            res["fraud_allowed_share"] = float((act[fraud] == "ALLOW").mean()) if fraud.any() else 0.0
            res["legit_allowed_share"] = float((act[legit] == "ALLOW").mean()) if legit.any() else 0.0
        return res

    def to_dict(self) -> Dict:
        return {"operating_threshold": self.operating_threshold,
                "anchor_score": self.anchor_score,
                "bands": [{"name": b.name, "lower": b.lower, "upper": b.upper,
                           "action": b.action, "description": b.description}
                          for b in self.bands]}
