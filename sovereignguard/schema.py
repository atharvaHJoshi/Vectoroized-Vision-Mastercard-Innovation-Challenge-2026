"""
Canonical schemas.

The single most important rule in this file:

    EVENT COLUMNS are produced by the generators.
    FEATURE COLUMNS are derived from event columns by features.py.
    The model may ONLY see FEATURE COLUMNS.

`fraud_label`, `attack_type`, `attack_id`, `attack_stage` and `difficulty` are
LABEL columns. They are never features. features.py asserts this.
"""
from __future__ import annotations

from typing import List

# ---------------------------------------------------------------- entities
CUSTOMER_COLUMNS: List[str] = [
    "customer_id", "persona", "age", "country", "home_city",
    "home_lat", "home_lon", "occupation", "account_age_days",
    "median_amount", "amount_sigma", "txns_per_day",
    "preferred_method", "primary_device_id", "n_devices",
    "night_activity", "travel_propensity", "new_merchant_rate",
    "kyc_level", "credit_limit", "is_synthetic_identity",
    "identity_doc_score", "contactability_score", "digital_footprint_days",
]

MERCHANT_COLUMNS: List[str] = [
    "merchant_id", "merchant_name", "category", "merchant_size",
    "merchant_age_days", "city", "lat", "lon",
    "median_ticket", "ticket_sigma", "daily_volume",
    "intrinsic_risk", "cnp_share", "chargeback_rate",
    "is_fraud_merchant", "onboarded_via",
]

DEVICE_COLUMNS: List[str] = [
    "device_id", "owner_customer_id", "os_family", "device_class",
    "first_seen_day", "is_emulator", "is_rooted", "reputation",
]

# ---------------------------------------------------------------- events
# The raw event stream. This is what a payment switch would actually emit.
EVENT_COLUMNS: List[str] = [
    "transaction_id",
    "customer_id",
    "merchant_id",
    "timestamp",              # int64 unix seconds
    "amount",
    "payment_method",
    "channel",                # POS / ECOM / APP / API
    "transaction_type",       # PURCHASE / TRANSFER / WITHDRAWAL / TOPUP
    "device_id",
    "city",
    "lat",
    "lon",
    "beneficiary_id",         # for transfers; '' otherwise
    "auth_result",            # APPROVED / DECLINED_AUTH / DECLINED_LIMIT
    "mcc_category",
    "session_id",
    # session/account-level context flags emitted by the auth system
    "password_changed_recently",
    "profile_changed_recently",
    "failed_logins_1h",
    "session_duration_s",
    "typing_cadence_dev",     # behavioural biometric deviation 0..1
    "ip_asn_type",            # RESIDENTIAL / MOBILE / HOSTING / VPN
    "is_new_beneficiary",
    "sim_swapped_recently",
    "inbound_call_active",    # phone-in-progress signal (social engineering)
    "payment_link_referred",  # payment initiated from an inbound link
]

LABEL_COLUMNS: List[str] = [
    "fraud_label", "attack_type", "attack_id", "attack_stage", "difficulty",
    "generator", "campaign_id",
]

TRANSACTION_COLUMNS: List[str] = EVENT_COLUMNS + LABEL_COLUMNS

# ---------------------------------------------------------------- features
# Ordered, explicit, and stable. The model contract is this list.
FEATURE_COLUMNS: List[str] = [
    # --- amount
    "amount",
    "amount_log",
    "amount_ratio_customer_median",
    "amount_zscore_customer",
    "amount_ratio_merchant_median",
    "amount_ratio_max_7d",
    "amount_round_number",
    "amount_pct_of_credit_limit",
    "amount_ratio_p95_30d",
    # --- velocity
    "txns_last_10min",
    "txns_last_1h",
    "txns_last_24h",
    "txns_last_7d",
    "amount_sum_1h",
    "amount_sum_24h",
    "amount_sum_24h_ratio_median_day",
    "seconds_since_prev_txn",
    "distinct_merchants_24h",
    "distinct_devices_24h",
    "distinct_cities_24h",
    "declines_last_24h",
    "escalating_amount_run",
    # --- device
    "is_new_device",
    "device_age_days",
    "device_txn_count",
    "device_share_of_customer",
    "is_emulator",
    "is_rooted",
    "device_reputation",
    # --- location
    "is_new_city",
    "distance_from_home_km",
    "distance_from_prev_txn_km",
    "implied_speed_kmh",
    "is_high_risk_location",
    "city_txn_count",
    # --- merchant
    "is_new_merchant",
    "merchant_intrinsic_risk",
    "merchant_age_days",
    "merchant_chargeback_rate",
    "merchant_cnp_share",
    "merchant_daily_volume_log",
    "customer_merchant_txn_count",
    "category_affinity_score",
    # --- temporal
    "hour_of_day",
    "day_of_week",
    "is_night",
    "is_weekend",
    "hour_deviation_from_profile",
    "is_unusual_hour_for_customer",
    # --- account / identity
    "account_age_days",
    "kyc_level_ord",
    "identity_doc_score",
    "contactability_score",
    "digital_footprint_days",
    "customer_lifetime_txns",
    # --- session / auth
    "password_changed_recently",
    "profile_changed_recently",
    "failed_logins_1h",
    "session_duration_s",
    "typing_cadence_dev",
    "ip_asn_is_hosting",
    "ip_asn_is_vpn",
    "is_new_beneficiary",
    "beneficiary_age_seconds",
    "sim_swapped_recently",
    "inbound_call_active",
    "payment_link_referred",
    # --- method / channel one-hots
    "method_UPI",
    "method_CARD",
    "method_WALLET",
    "method_NETBANKING",
    "channel_ECOM",
    "channel_POS",
    "channel_APP",
    "channel_API",
    "type_TRANSFER",
    "type_WITHDRAWAL",
    "type_PURCHASE",
    "type_TOPUP",
    # --- sequence / graph
    "seq_stage_index",
    "customer_risk_events_24h",
    "beneficiary_indegree_24h",
    "merchant_new_customer_share_24h",
]

# Human-readable names for the explanation layer.
FEATURE_LABELS = {
    "amount": "Transaction amount",
    "amount_log": "Transaction amount (log)",
    "amount_ratio_customer_median": "Amount vs. customer's normal amount",
    "amount_zscore_customer": "Amount z-score against customer history",
    "amount_ratio_merchant_median": "Amount vs. merchant's typical ticket",
    "amount_ratio_max_7d": "Amount vs. customer's 7-day maximum",
    "amount_round_number": "Suspiciously round amount",
    "amount_pct_of_credit_limit": "Amount as share of credit limit",
    "amount_ratio_p95_30d": "Amount vs. customer's 30-day 95th percentile",
    "txns_last_10min": "Transactions in the last 10 minutes",
    "txns_last_1h": "Transactions in the last hour",
    "txns_last_24h": "Transactions in the last 24 hours",
    "txns_last_7d": "Transactions in the last 7 days",
    "amount_sum_1h": "Value transacted in the last hour",
    "amount_sum_24h": "Value transacted in the last 24 hours",
    "amount_sum_24h_ratio_median_day": "24-hour value vs. normal daily value",
    "seconds_since_prev_txn": "Time since previous transaction",
    "distinct_merchants_24h": "Distinct merchants in 24 hours",
    "distinct_devices_24h": "Distinct devices in 24 hours",
    "distinct_cities_24h": "Distinct cities in 24 hours",
    "declines_last_24h": "Declined attempts in 24 hours",
    "escalating_amount_run": "Consecutive increasing-amount run",
    "is_new_device": "First transaction from this device",
    "device_age_days": "Age of device on this account",
    "device_txn_count": "Prior transactions from this device",
    "device_share_of_customer": "Share of customer activity on this device",
    "is_emulator": "Device is an emulator",
    "is_rooted": "Device is rooted / jailbroken",
    "device_reputation": "Device reputation score",
    "is_new_city": "First transaction from this city",
    "distance_from_home_km": "Distance from home city",
    "distance_from_prev_txn_km": "Distance from previous transaction",
    "implied_speed_kmh": "Implied travel speed since last transaction",
    "is_high_risk_location": "High-risk location",
    "city_txn_count": "Prior transactions in this city",
    "is_new_merchant": "Never-before-seen merchant",
    "merchant_intrinsic_risk": "Merchant category risk",
    "merchant_age_days": "How long the merchant has existed",
    "merchant_chargeback_rate": "Merchant chargeback rate",
    "merchant_cnp_share": "Merchant card-not-present share",
    "merchant_daily_volume_log": "Merchant daily volume",
    "customer_merchant_txn_count": "Prior transactions with this merchant",
    "category_affinity_score": "Fit with customer's usual categories",
    "hour_of_day": "Hour of day",
    "day_of_week": "Day of week",
    "is_night": "Overnight transaction",
    "is_weekend": "Weekend transaction",
    "hour_deviation_from_profile": "Hour differs from customer's pattern",
    "is_unusual_hour_for_customer": "Unusual hour for this customer",
    "account_age_days": "Account age",
    "kyc_level_ord": "KYC verification level",
    "identity_doc_score": "Identity document confidence",
    "contactability_score": "Contactability of the identity",
    "digital_footprint_days": "Age of the identity's digital footprint",
    "customer_lifetime_txns": "Customer's lifetime transaction count",
    "password_changed_recently": "Password changed recently",
    "profile_changed_recently": "Profile details changed recently",
    "failed_logins_1h": "Failed logins in the last hour",
    "session_duration_s": "Session duration",
    "typing_cadence_dev": "Behavioural-biometric deviation",
    "ip_asn_is_hosting": "Traffic from hosting/datacentre IP",
    "ip_asn_is_vpn": "Traffic from VPN",
    "is_new_beneficiary": "Newly added beneficiary",
    "beneficiary_age_seconds": "Age of the beneficiary record",
    "sim_swapped_recently": "Recent SIM swap",
    "inbound_call_active": "Call in progress during payment",
    "payment_link_referred": "Payment started from an inbound link",
    "method_UPI": "Paid by UPI",
    "method_CARD": "Paid by card",
    "method_WALLET": "Paid by wallet",
    "method_NETBANKING": "Paid by net banking",
    "channel_ECOM": "E-commerce channel",
    "channel_POS": "In-person channel",
    "channel_APP": "In-app channel",
    "channel_API": "API-initiated",
    "type_TRANSFER": "Account-to-account transfer",
    "type_WITHDRAWAL": "Withdrawal",
    "type_PURCHASE": "Purchase",
    "type_TOPUP": "Wallet top-up",
    "seq_stage_index": "Position in the customer's recent action sequence",
    "customer_risk_events_24h": "Risk events on the account in 24 hours",
    "beneficiary_indegree_24h": "Distinct payers to this beneficiary in 24 hours",
    "merchant_new_customer_share_24h": "Merchant's share of first-time customers",
}

# Sanity: every feature must have a label.
_missing = [c for c in FEATURE_COLUMNS if c not in FEATURE_LABELS]
if _missing:  # pragma: no cover
    raise RuntimeError(f"FEATURE_LABELS missing entries for: {_missing}")

FORBIDDEN_IN_FEATURES = set(LABEL_COLUMNS)
_leak = FORBIDDEN_IN_FEATURES & set(FEATURE_COLUMNS)
if _leak:  # pragma: no cover
    raise RuntimeError(f"Label leakage in FEATURE_COLUMNS: {_leak}")

KYC_LEVELS = {"MIN": 0, "BASIC": 1, "FULL": 2, "ENHANCED": 3}
