from __future__ import annotations

MODEL_VERSION = "predictive_layer_v2"
STRATEGY_KEY = "deterministic_modular_prediction_run"

SCENARIO_DEFAULTS: dict[str, dict[str, float | int]] = {
    "base": {
        "quoteMultiplier": 1.0,
        "actualMultiplier": 1.0,
        "varianceDeltaPct": 0.0,
        "winProbabilityDeltaPct": 0.0,
        "scheduleShiftMonths": 0,
        "thirdPartyCostDeltaPct": 0.0,
    },
    "upside": {
        "quoteMultiplier": 1.05,
        "actualMultiplier": 1.04,
        "varianceDeltaPct": -3.0,
        "winProbabilityDeltaPct": 8.0,
        "scheduleShiftMonths": 0,
        "thirdPartyCostDeltaPct": -5.0,
    },
    "downside": {
        "quoteMultiplier": 0.92,
        "actualMultiplier": 0.9,
        "varianceDeltaPct": 6.0,
        "winProbabilityDeltaPct": -12.0,
        "scheduleShiftMonths": 1,
        "thirdPartyCostDeltaPct": 8.0,
    },
}

SCENARIO_TITLES = {
    "base": "Base Case",
    "upside": "Upside Case",
    "downside": "Downside Case",
}

FALLBACK_TIERS = [
    "in_flight_actuals",
    "high_similarity_history",
    "same_client_format_budget_band",
    "same_project_type_all_clients",
    "discipline_baseline",
    "system_default",
]

MATURITY_STAGES = {
    "stage_1": "early_opportunity",
    "stage_2": "quote_development",
    "stage_3": "awarded_or_booked",
    "stage_4": "in_flight",
}
