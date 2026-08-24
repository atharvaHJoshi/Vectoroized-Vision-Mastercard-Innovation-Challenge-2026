"""
SovereignGuard — central configuration.

Everything tunable about the simulation lives here so experiments are
reproducible from a single seed + scale profile.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("SG_DATA_DIR", ROOT / "data"))
SYNTHETIC_DIR = DATA_DIR / "synthetic"
ATTACKS_DIR = DATA_DIR / "attacks"
EVAL_DIR = DATA_DIR / "evaluation"
MODELS_DIR = Path(os.environ.get("SG_MODELS_DIR", ROOT / "models"))
EXPERIMENTS_DIR = Path(os.environ.get("SG_EXPERIMENTS_DIR", ROOT / "experiments" / "results"))

# The database deliberately does NOT default into the repo/data directory.
# SQLite needs POSIX file locking, which network mounts, container bind mounts
# and cloud-synced folders (Dropbox/OneDrive/virtiofs) frequently do not provide
# — you get "disk I/O error" on the very first write. A local state directory
# avoids that class of failure entirely. Override with SG_DB_PATH.
def _default_state_dir() -> Path:
    if os.environ.get("SG_STATE_DIR"):
        return Path(os.environ["SG_STATE_DIR"])
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(base) / "sovereignguard"


STATE_DIR = _default_state_dir()
DB_PATH = Path(os.environ.get("SG_DB_PATH", STATE_DIR / "sovereignguard.db"))

for _d in (SYNTHETIC_DIR, ATTACKS_DIR, EVAL_DIR, MODELS_DIR, EXPERIMENTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
try:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
except OSError:  # pragma: no cover - unwritable home; Store() falls back to tmp
    pass


# --------------------------------------------------------------------------
# Scale profiles
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ScaleProfile:
    name: str
    n_customers: int
    n_merchants: int
    n_days: int
    attacks_per_type: int

    @property
    def approx_transactions(self) -> int:
        return int(self.n_customers * self.n_days * 2.6)


SCALES: Dict[str, ScaleProfile] = {
    # 'nano' exists so the full experiment suite can run inside a short time
    # budget (CI, sandboxes, laptops). It is sized so a test window still holds
    # ~100+ fraud events, which keeps recall estimates meaningful; below roughly
    # this size single-segment recall becomes sampling noise.
    "nano": ScaleProfile("nano", 300, 200, 21, 80),
    "tiny": ScaleProfile("tiny", 400, 300, 30, 120),
    "demo": ScaleProfile("demo", 2_000, 1_200, 45, 400),
    "large": ScaleProfile("large", 10_000, 4_000, 60, 1_200),
    "full": ScaleProfile("full", 100_000, 20_000, 90, 4_000),
}

DEFAULT_SCALE = os.environ.get("SG_SCALE", "demo")
SEED = int(os.environ.get("SG_SEED", "20260823"))


# --------------------------------------------------------------------------
# Behavioural personas
#
# These drive *all* legitimate behaviour. Realistic legitimate behaviour is
# what makes the fraud detection problem hard and the false-positive metric
# meaningful, so this is deliberately detailed.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Persona:
    name: str
    weight: float
    age_range: tuple
    # lognormal params for transaction amount in INR
    amount_mu: float
    amount_sigma: float
    txns_per_day: float
    account_age_days_range: tuple
    n_devices_range: tuple
    method_weights: Dict[str, float]
    category_affinity: Dict[str, float]
    night_activity: float          # P(transaction between 00:00-06:00)
    travel_propensity: float       # P(customer takes a trip in the window)
    new_merchant_rate: float       # P(a given txn is at a never-seen merchant)
    device_change_rate: float      # P(customer legitimately switches device in window)
    transfer_share: float          # share of activity that is A2A transfer / P2P


PERSONAS: List[Persona] = [
    Persona(
        name="STUDENT",
        weight=0.16,
        age_range=(18, 25),
        amount_mu=5.55, amount_sigma=0.80,          # median ~ INR 257
        txns_per_day=3.4,
        account_age_days_range=(60, 900),
        n_devices_range=(1, 2),
        method_weights={"UPI": 0.62, "CARD": 0.22, "WALLET": 0.14, "NETBANKING": 0.02},
        category_affinity={
            "FOOD": 0.24, "ECOMMERCE": 0.14, "ENTERTAINMENT": 0.12, "GAMING": 0.11,
            "MOBILITY": 0.10, "GROCERY": 0.09, "EDUCATION": 0.07, "UTILITIES": 0.05,
            "FUEL": 0.03, "P2P_TRANSFER": 0.03, "TRAVEL": 0.01, "HEALTHCARE": 0.01,
        },
        night_activity=0.17, travel_propensity=0.22, new_merchant_rate=0.17,
        device_change_rate=0.10, transfer_share=0.06,
    ),
    Persona(
        name="YOUNG_PROFESSIONAL",
        weight=0.22,
        age_range=(24, 34),
        amount_mu=6.55, amount_sigma=0.92,          # median ~ INR 700
        txns_per_day=4.1,
        account_age_days_range=(200, 2200),
        n_devices_range=(1, 3),
        method_weights={"UPI": 0.48, "CARD": 0.34, "WALLET": 0.10, "NETBANKING": 0.08},
        category_affinity={
            "FOOD": 0.19, "ECOMMERCE": 0.15, "MOBILITY": 0.12, "GROCERY": 0.11,
            "ENTERTAINMENT": 0.09, "TRAVEL": 0.07, "UTILITIES": 0.07, "FUEL": 0.06,
            "P2P_TRANSFER": 0.05, "HEALTHCARE": 0.04, "FINANCIAL_SERVICES": 0.03,
            "GAMING": 0.02,
        },
        night_activity=0.11, travel_propensity=0.34, new_merchant_rate=0.14,
        device_change_rate=0.12, transfer_share=0.10,
    ),
    Persona(
        name="FAMILY",
        weight=0.21,
        age_range=(32, 50),
        amount_mu=7.05, amount_sigma=0.88,          # median ~ INR 1155
        txns_per_day=3.0,
        account_age_days_range=(500, 4000),
        n_devices_range=(2, 3),
        method_weights={"UPI": 0.40, "CARD": 0.36, "NETBANKING": 0.18, "WALLET": 0.06},
        category_affinity={
            "GROCERY": 0.24, "UTILITIES": 0.14, "FOOD": 0.11, "HEALTHCARE": 0.10,
            "EDUCATION": 0.10, "ECOMMERCE": 0.09, "FUEL": 0.07, "MOBILITY": 0.05,
            "P2P_TRANSFER": 0.04, "TRAVEL": 0.03, "ENTERTAINMENT": 0.03,
        },
        night_activity=0.05, travel_propensity=0.28, new_merchant_rate=0.09,
        device_change_rate=0.08, transfer_share=0.09,
    ),
    Persona(
        name="SENIOR",
        weight=0.12,
        age_range=(58, 78),
        amount_mu=6.85, amount_sigma=0.72,
        txns_per_day=1.3,
        account_age_days_range=(1500, 7000),
        n_devices_range=(1, 2),
        method_weights={"NETBANKING": 0.36, "CARD": 0.30, "UPI": 0.30, "WALLET": 0.04},
        category_affinity={
            "HEALTHCARE": 0.24, "GROCERY": 0.20, "UTILITIES": 0.18, "P2P_TRANSFER": 0.10,
            "FOOD": 0.07, "ECOMMERCE": 0.06, "TRAVEL": 0.05, "FINANCIAL_SERVICES": 0.05,
            "FUEL": 0.03, "MOBILITY": 0.02,
        },
        night_activity=0.02, travel_propensity=0.14, new_merchant_rate=0.05,
        device_change_rate=0.04, transfer_share=0.14,
    ),
    Persona(
        name="GIG_WORKER",
        weight=0.11,
        age_range=(21, 40),
        amount_mu=5.95, amount_sigma=0.85,
        txns_per_day=5.6,
        account_age_days_range=(90, 1500),
        n_devices_range=(1, 2),
        method_weights={"UPI": 0.72, "WALLET": 0.16, "CARD": 0.09, "NETBANKING": 0.03},
        category_affinity={
            "FUEL": 0.22, "FOOD": 0.19, "MOBILITY": 0.14, "GROCERY": 0.13,
            "P2P_TRANSFER": 0.11, "UTILITIES": 0.08, "ECOMMERCE": 0.06,
            "ENTERTAINMENT": 0.04, "HEALTHCARE": 0.03,
        },
        night_activity=0.21, travel_propensity=0.18, new_merchant_rate=0.19,
        device_change_rate=0.16, transfer_share=0.16,
    ),
    Persona(
        name="SMALL_BUSINESS",
        weight=0.10,
        age_range=(28, 55),
        amount_mu=8.10, amount_sigma=1.05,          # median ~ INR 3294
        txns_per_day=7.8,
        account_age_days_range=(300, 3600),
        n_devices_range=(2, 4),
        method_weights={"UPI": 0.44, "NETBANKING": 0.34, "CARD": 0.20, "WALLET": 0.02},
        category_affinity={
            "P2P_TRANSFER": 0.20, "FINANCIAL_SERVICES": 0.15, "ECOMMERCE": 0.14,
            "UTILITIES": 0.12, "FUEL": 0.10, "GROCERY": 0.09, "MOBILITY": 0.07,
            "FOOD": 0.06, "TRAVEL": 0.05, "HEALTHCARE": 0.02,
        },
        night_activity=0.09, travel_propensity=0.40, new_merchant_rate=0.22,
        device_change_rate=0.14, transfer_share=0.26,
    ),
    Persona(
        name="HIGH_NET_WORTH",
        weight=0.08,
        age_range=(35, 65),
        amount_mu=8.95, amount_sigma=1.20,          # median ~ INR 7725
        txns_per_day=2.6,
        account_age_days_range=(800, 6000),
        n_devices_range=(2, 4),
        method_weights={"CARD": 0.46, "NETBANKING": 0.30, "UPI": 0.22, "WALLET": 0.02},
        category_affinity={
            "TRAVEL": 0.20, "ECOMMERCE": 0.15, "FINANCIAL_SERVICES": 0.14,
            "ENTERTAINMENT": 0.10, "FOOD": 0.10, "HEALTHCARE": 0.09, "GROCERY": 0.08,
            "P2P_TRANSFER": 0.07, "UTILITIES": 0.04, "FUEL": 0.03,
        },
        night_activity=0.08, travel_propensity=0.62, new_merchant_rate=0.20,
        device_change_rate=0.18, transfer_share=0.18,
    ),
]

PERSONA_BY_NAME = {p.name: p for p in PERSONAS}


# --------------------------------------------------------------------------
# Merchant categories
#
# base_ticket / ticket_sigma are lognormal params for the category's own
# ticket-size distribution. The final amount blends customer and category.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class CategorySpec:
    name: str
    weight: float
    base_ticket: float
    ticket_sigma: float
    intrinsic_risk: float       # 0..1 baseline category risk
    cnp_share: float            # card-not-present / online share
    peak_hours: tuple


CATEGORIES: List[CategorySpec] = [
    CategorySpec("FOOD",               0.14, 5.85, 0.62, 0.10, 0.55, (12, 13, 19, 20, 21)),
    CategorySpec("GROCERY",            0.13, 6.55, 0.66, 0.07, 0.30, (10, 11, 18, 19, 20)),
    CategorySpec("ECOMMERCE",          0.12, 6.90, 0.95, 0.28, 0.98, (11, 13, 21, 22, 23)),
    CategorySpec("MOBILITY",           0.09, 5.30, 0.58, 0.12, 0.90, (9, 10, 18, 19, 20)),
    CategorySpec("UTILITIES",          0.09, 6.75, 0.58, 0.05, 0.85, (10, 11, 17, 18, 19)),
    CategorySpec("FUEL",               0.08, 6.45, 0.48, 0.09, 0.15, (8, 9, 18, 19)),
    CategorySpec("ENTERTAINMENT",      0.07, 5.95, 0.72, 0.16, 0.80, (19, 20, 21, 22)),
    CategorySpec("P2P_TRANSFER",       0.07, 7.30, 1.15, 0.34, 1.00, (11, 12, 18, 19, 20)),
    CategorySpec("TRAVEL",             0.06, 8.40, 1.05, 0.22, 0.92, (10, 11, 15, 16, 21)),
    CategorySpec("HEALTHCARE",         0.05, 7.10, 0.88, 0.08, 0.35, (10, 11, 12, 17, 18)),
    CategorySpec("EDUCATION",          0.04, 8.05, 0.92, 0.07, 0.70, (10, 11, 16, 17)),
    CategorySpec("GAMING",             0.03, 5.70, 0.90, 0.42, 1.00, (20, 21, 22, 23, 0)),
    CategorySpec("FINANCIAL_SERVICES", 0.02, 8.60, 1.10, 0.30, 0.95, (10, 11, 14, 15, 16)),
    CategorySpec("CRYPTO_GATEWAY",     0.01, 8.20, 1.25, 0.72, 1.00, (0, 1, 21, 22, 23)),
]

CATEGORY_BY_NAME = {c.name: c for c in CATEGORIES}
CATEGORY_NAMES = [c.name for c in CATEGORIES]

PAYMENT_METHODS = ["UPI", "CARD", "WALLET", "NETBANKING"]

# City -> (lat, lon, population weight). Distances drive geo-velocity features.
CITIES: Dict[str, tuple] = {
    "Mumbai":     (19.0760, 72.8777, 0.135),
    "Delhi":      (28.7041, 77.1025, 0.130),
    "Bengaluru":  (12.9716, 77.5946, 0.115),
    "Hyderabad":  (17.3850, 78.4867, 0.085),
    "Chennai":    (13.0827, 80.2707, 0.080),
    "Kolkata":    (22.5726, 88.3639, 0.070),
    "Pune":       (18.5204, 73.8567, 0.065),
    "Ahmedabad":  (23.0225, 72.5714, 0.055),
    "Jaipur":     (26.9124, 75.7873, 0.040),
    "Lucknow":    (26.8467, 80.9462, 0.033),
    "Kochi":      ( 9.9312, 76.2673, 0.030),
    "Chandigarh": (30.7333, 76.7794, 0.028),
    "Indore":     (22.7196, 75.8577, 0.026),
    "Bhubaneswar":(20.2961, 85.8245, 0.022),
    "Guwahati":   (26.1445, 91.7362, 0.020),
    "Coimbatore": (11.0168, 76.9558, 0.020),
    "Nagpur":     (21.1458, 79.0882, 0.019),
    "Surat":      (21.1702, 72.8311, 0.019),
    "Dubai":      (25.2048, 55.2708, 0.007),
    "Singapore":  ( 1.3521,103.8198, 0.006),
}
CITY_NAMES = list(CITIES.keys())

# Locations attackers like to operate from (cheap hosting / mule geography).
HIGH_RISK_LOCATIONS = ["Dubai", "Singapore", "Guwahati", "Lucknow"]


# --------------------------------------------------------------------------
# Legitimate "life event" rates.
#
# WHY THIS MATTERS: if only fraudsters ever changed device, added a payee or
# travelled, those flags would be perfect fraud oracles and the whole
# experiment would be meaningless. Real customers do these things too.
# --------------------------------------------------------------------------
LEGIT_EVENT_RATES = {
    "password_change_per_year": 0.85,
    "profile_change_per_year": 1.6,
    "new_beneficiary_per_year": 5.2,
    "failed_login_burst_per_year": 3.1,
    "large_purchase_share": 0.021,      # share of txns at 5x-18x customer median
    "device_reinstall_per_year": 1.4,
}


# --------------------------------------------------------------------------
# Risk decision policy (prototype thresholds — tunable, not Mastercard's)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class RiskBand:
    name: str
    lower: float
    upper: float
    action: str
    description: str


RISK_BANDS: List[RiskBand] = [
    RiskBand("LOW", 0.0, 30.0, "ALLOW",
             "Approve straight through. No customer friction."),
    RiskBand("MEDIUM", 30.0, 60.0, "MONITOR",
             "Approve but log for behavioural monitoring and post-hoc review."),
    RiskBand("HIGH", 60.0, 80.0, "STEP_UP_AUTH",
             "Challenge with step-up authentication before settlement."),
    RiskBand("CRITICAL", 80.0, 100.01, "HOLD_REVIEW",
             "Hold the payment and route to a fraud analyst queue."),
]

# Operating point: the detector's decision threshold is chosen on the
# validation set as the highest-recall threshold whose false-positive rate on
# legitimate traffic stays at or below this budget.
TARGET_FPR_BUDGET = float(os.environ.get("SG_TARGET_FPR", "0.010"))


# --------------------------------------------------------------------------
# Attack difficulty
# --------------------------------------------------------------------------
DIFFICULTIES = ["EASY", "MEDIUM", "HARD", "ADVERSARIAL"]

ATTACK_TYPES = [
    "ACCOUNT_TAKEOVER",
    "TRANSACTION_MANIPULATION",
    "SYNTHETIC_IDENTITY",
    "MERCHANT_FRAUD",
    "PHISHING_PAYMENT_LINK",
    "SOCIAL_ENGINEERING",
    "MULTI_STAGE",
]


@dataclass
class RunConfig:
    """Everything needed to reproduce a full pipeline run."""
    scale: str = DEFAULT_SCALE
    seed: int = SEED
    attack_types: List[str] = field(default_factory=lambda: list(ATTACK_TYPES))
    difficulty_mix: Dict[str, float] = field(
        default_factory=lambda: {"EASY": 0.25, "MEDIUM": 0.40, "HARD": 0.35}
    )
    target_fpr: float = TARGET_FPR_BUDGET

    @property
    def profile(self) -> ScaleProfile:
        return SCALES[self.scale]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["approx_transactions"] = self.profile.approx_transactions
        return d
