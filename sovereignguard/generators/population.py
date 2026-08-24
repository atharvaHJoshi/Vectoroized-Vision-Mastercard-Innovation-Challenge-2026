"""Synthetic population: customers, merchants, devices.

Everything here is drawn from persona / category distributions in config.py so
that legitimate behaviour is *structured* rather than uniform noise. Structured
legitimate behaviour is what makes the detection problem non-trivial.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C
from ..rng import substream, weighted_choice
from ..schema import CUSTOMER_COLUMNS, MERCHANT_COLUMNS, DEVICE_COLUMNS

OCCUPATIONS = {
    "STUDENT": ["Student", "Intern", "Research Assistant"],
    "YOUNG_PROFESSIONAL": ["Software Engineer", "Analyst", "Designer", "Consultant",
                           "Marketing Executive", "Nurse", "Teacher"],
    "FAMILY": ["Operations Manager", "Teacher", "Civil Servant", "Accountant",
               "Sales Manager", "Pharmacist", "Engineer"],
    "SENIOR": ["Retired", "Pensioner", "Part-time Consultant"],
    "GIG_WORKER": ["Delivery Partner", "Cab Driver", "Freelancer", "Field Agent"],
    "SMALL_BUSINESS": ["Shop Owner", "Restaurateur", "Trader", "Contractor",
                       "Wholesaler", "Pharmacy Owner"],
    "HIGH_NET_WORTH": ["Business Owner", "Investor", "Surgeon", "Partner (Law)",
                       "Senior Executive"],
}

MERCHANT_WORDS = {
    "FOOD": ["Kitchen", "Diner", "Cafe", "Biryani House", "Tiffin", "Grill", "Chai Point"],
    "GROCERY": ["Mart", "Bazaar", "Fresh", "Provision Store", "Supermart", "Kirana"],
    "ECOMMERCE": ["Cart", "Shop", "Store", "Bazaar Online", "Trends", "Outlet"],
    "MOBILITY": ["Rides", "Cabs", "Metro", "Auto", "Transit"],
    "UTILITIES": ["Power", "Water Board", "Broadband", "Gas", "Municipal"],
    "FUEL": ["Fuels", "Petro", "Filling Station", "Energy"],
    "ENTERTAINMENT": ["Cinemas", "Studio", "Play", "Arena", "Stream"],
    "P2P_TRANSFER": ["Transfer", "Payout", "Remit", "Settle"],
    "TRAVEL": ["Travels", "Holidays", "Airways", "Stays", "Tours"],
    "HEALTHCARE": ["Clinic", "Diagnostics", "Pharmacy", "Hospital", "Labs"],
    "EDUCATION": ["Academy", "Institute", "Tutorials", "Learning", "College"],
    "GAMING": ["Games", "Arena", "Coins", "Play Hub", "Esports"],
    "FINANCIAL_SERVICES": ["Capital", "Finserv", "Advisors", "Securities", "Lending"],
    "CRYPTO_GATEWAY": ["Exchange", "Wallet", "Chain", "Digital Assets"],
}
MERCHANT_PREFIX = ["Sri", "New", "Royal", "Metro", "Prime", "Star", "Green", "Urban",
                   "Sunrise", "Golden", "Blue", "Nova", "Apex", "Silver", "Grand"]


# ------------------------------------------------------------------ helpers
def _city_arrays():
    names = C.CITY_NAMES
    lats = np.array([C.CITIES[n][0] for n in names])
    lons = np.array([C.CITIES[n][1] for n in names])
    w = np.array([C.CITIES[n][2] for n in names], dtype=float)
    return names, lats, lons, w / w.sum()


# ------------------------------------------------------------------ customers
def generate_customers(n: int, seed: int) -> pd.DataFrame:
    rng = substream(seed, "customers")
    names, lats, lons, cw = _city_arrays()

    persona_names = [p.name for p in C.PERSONAS]
    persona_w = np.array([p.weight for p in C.PERSONAS], dtype=float)
    persona_w /= persona_w.sum()
    assigned = rng.choice(len(C.PERSONAS), size=n, p=persona_w)

    rows = []
    for i in range(n):
        p = C.PERSONAS[assigned[i]]
        age = int(rng.integers(p.age_range[0], p.age_range[1] + 1))
        ci = int(rng.choice(len(names), p=cw))
        city = names[ci]

        # Per-customer amount profile: persona median jittered per individual so
        # two students still differ from each other.
        mu = p.amount_mu + rng.normal(0.0, 0.28)
        sigma = max(0.35, p.amount_sigma * rng.uniform(0.8, 1.25))
        median_amount = float(np.exp(mu))

        acct_lo, acct_hi = p.account_age_days_range
        # Beta skews toward newer accounts (realistic acquisition curve).
        account_age = int(acct_lo + rng.beta(1.7, 2.3) * (acct_hi - acct_lo))
        # A real portfolio is always acquiring: roughly 12% of accounts are less
        # than a few months old at any moment.
        #
        # LEAKAGE NOTE: without these genuinely-new accounts, every young
        # account in the dataset is a fabricated identity, and `account_age_days`
        # plus `digital_footprint_days` become near-perfect oracles for
        # SYNTHETIC_IDENTITY (measured at AUC 0.99+). Recent honest signups are
        # what force the model to distinguish "new" from "fake".
        if rng.random() < 0.12:
            account_age = int(rng.integers(5, 200))

        txns_per_day = float(max(0.25, p.txns_per_day * rng.gamma(6.0, 1 / 6.0)))
        n_devices = int(rng.integers(p.n_devices_range[0], p.n_devices_range[1] + 1))

        # KYC correlates with account age and persona affluence.
        kyc_score = (account_age / 3000.0) + (0.4 if p.name in
                     ("HIGH_NET_WORTH", "SMALL_BUSINESS", "FAMILY") else 0.0)
        kyc = ("ENHANCED" if kyc_score > 1.05 else
               "FULL" if kyc_score > 0.55 else
               "BASIC" if kyc_score > 0.2 else "MIN")

        credit_limit = float(np.clip(median_amount * rng.uniform(14, 55), 8_000, 4_000_000))

        rows.append({
            "customer_id": f"CUST_{i:07d}",
            "persona": p.name,
            "age": age,
            "country": "IN" if city not in ("Dubai", "Singapore") else ("AE" if city == "Dubai" else "SG"),
            "home_city": city,
            "home_lat": float(lats[ci]),
            "home_lon": float(lons[ci]),
            "occupation": str(rng.choice(OCCUPATIONS[p.name])),
            "account_age_days": account_age,
            "median_amount": round(median_amount, 2),
            "amount_sigma": round(sigma, 4),
            "txns_per_day": round(txns_per_day, 3),
            "preferred_method": str(weighted_choice(rng, p.method_weights)),
            "primary_device_id": f"DEV_{i:07d}_0",
            "n_devices": n_devices,
            "night_activity": p.night_activity,
            "travel_propensity": p.travel_propensity,
            "new_merchant_rate": p.new_merchant_rate,
            "kyc_level": kyc,
            "credit_limit": round(credit_limit, 2),
            # Genuine customers: real documents, contactable, long footprint.
            #
            # LEAKAGE NOTE: these distributions must OVERLAP the fabricated ones
            # in families.py::gen_synthetic_identity, or origination signals
            # become perfect oracles. Real portfolios contain plenty of genuine
            # customers with poor document scans, stale contact details and thin
            # files — recent migrants, young adults, people who onboarded in a
            # hurry. Beta(4, 2.2) has a long left tail for exactly that reason;
            # a tighter distribution would make this problem artificially easy.
            "is_synthetic_identity": 0,
            "identity_doc_score": round(float(np.clip(rng.beta(4.0, 2.2), 0.05, 1.0)), 4),
            "contactability_score": round(float(np.clip(rng.beta(3.5, 2.4), 0.02, 1.0)), 4),
            # Footprint as a multiple of account age (1.3x-5x), matching the
            # ratio-based construction used for synthetic identities.
            "digital_footprint_days": int(account_age * rng.uniform(1.3, 5.0)) + 30,
        })

    df = pd.DataFrame(rows)[CUSTOMER_COLUMNS]
    return df


# ------------------------------------------------------------------ merchants
def generate_merchants(n: int, seed: int) -> pd.DataFrame:
    rng = substream(seed, "merchants")
    names, lats, lons, cw = _city_arrays()

    cat_names = [c.name for c in C.CATEGORIES]
    cat_w = np.array([c.weight for c in C.CATEGORIES], dtype=float)
    cat_w /= cat_w.sum()
    assigned = rng.choice(len(C.CATEGORIES), size=n, p=cat_w)

    rows = []
    for i in range(n):
        spec = C.CATEGORIES[assigned[i]]
        ci = int(rng.choice(len(names), p=cw))
        # Merchant size follows a power law: many small, few very large.
        size_draw = rng.pareto(1.35) + 1.0
        size = ("ENTERPRISE" if size_draw > 9 else
                "LARGE" if size_draw > 4 else
                "MEDIUM" if size_draw > 1.9 else "SMALL")
        daily_volume = float(np.clip(size_draw * rng.uniform(9, 140), 3, 260_000))
        age_days = int(np.clip(rng.gamma(2.1, 520), 3, 7300))

        # Chargeback rate rises with category risk and falls with age/size.
        cb = float(np.clip(
            spec.intrinsic_risk * rng.uniform(0.004, 0.05) * (900.0 / (age_days + 250.0)),
            0.0, 0.35))

        word = str(rng.choice(MERCHANT_WORDS[spec.name]))
        pre = str(rng.choice(MERCHANT_PREFIX))
        rows.append({
            "merchant_id": f"MER_{i:06d}",
            "merchant_name": f"{pre} {word}",
            "category": spec.name,
            "merchant_size": size,
            "merchant_age_days": age_days,
            "city": names[ci],
            "lat": float(lats[ci]),
            "lon": float(lons[ci]),
            "median_ticket": round(float(np.exp(spec.base_ticket + rng.normal(0, 0.3))), 2),
            "ticket_sigma": round(float(spec.ticket_sigma * rng.uniform(0.85, 1.2)), 4),
            "daily_volume": round(daily_volume, 1),
            "intrinsic_risk": round(float(np.clip(spec.intrinsic_risk * rng.uniform(0.7, 1.35), 0, 1)), 4),
            "cnp_share": round(float(np.clip(spec.cnp_share * rng.uniform(0.85, 1.12), 0, 1)), 4),
            "chargeback_rate": round(cb, 5),
            "is_fraud_merchant": 0,
            "onboarded_via": str(rng.choice(["BRANCH", "SELF_SERVE", "AGGREGATOR", "PARTNER"],
                                            p=[0.18, 0.42, 0.30, 0.10])),
        })

    return pd.DataFrame(rows)[MERCHANT_COLUMNS]


# ------------------------------------------------------------------ devices
def generate_devices(customers: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = substream(seed, "devices")
    rows = []
    for cust in customers.itertuples(index=False):
        for k in range(int(cust.n_devices)):
            first_seen = 0 if k == 0 else int(rng.integers(0, max(1, cust.account_age_days)))
            rows.append({
                "device_id": f"DEV_{int(cust.customer_id.split('_')[1]):07d}_{k}",
                "owner_customer_id": cust.customer_id,
                "os_family": str(rng.choice(["ANDROID", "IOS", "WINDOWS", "MACOS"],
                                            p=[0.66, 0.22, 0.09, 0.03])),
                "device_class": str(rng.choice(["PHONE", "TABLET", "DESKTOP"], p=[0.85, 0.07, 0.08])),
                "first_seen_day": first_seen,
                "is_emulator": 0,
                "is_rooted": int(rng.random() < 0.026),   # some genuine users root phones
                "reputation": round(float(np.clip(rng.beta(7.5, 1.7), 0.02, 1.0)), 4),
            })
    return pd.DataFrame(rows)[DEVICE_COLUMNS]


def build_population(n_customers: int, n_merchants: int, seed: int):
    customers = generate_customers(n_customers, seed)
    merchants = generate_merchants(n_merchants, seed)
    devices = generate_devices(customers, seed)
    return customers, merchants, devices
