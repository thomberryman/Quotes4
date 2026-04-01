# Predictive Layer Sample Outputs

These examples are illustrative reference payloads for realistic post production use cases.
They show the intended shape and decision style of the matured predictive layer, not locked golden fixtures.

## 1. Sparse Early Trailer Bid

- Maturity stage: `stage_1`
- Evidence source: `comparables`
- Fallback tier: `same_project_type_all_clients`

```json
{
  "likelyQuoteRange": {
    "basis": "comparable_quote_history",
    "low": 82000,
    "median": 96000,
    "high": 118000,
    "recommendedMedian": 98900,
    "confidence": "medium"
  },
  "winProbability": {
    "probabilityPct": 38,
    "probabilityBand": "low",
    "confidence": "medium"
  },
  "missingCriticalInputs": [
    "project_format_key",
    "disciplines",
    "schedule_dates"
  ],
  "disciplineUsageHighlights": [
    {
      "disciplineCode": "offline",
      "usageRatePct": 92,
      "predictedSharePct": 44
    },
    {
      "disciplineCode": "online",
      "usageRatePct": 79,
      "predictedSharePct": 31
    }
  ]
}
```

## 2. Awarded Episodic Localisation Project

- Maturity stage: `stage_3`
- Evidence source: `comparables`
- Fallback tier: `high_similarity_history`

```json
{
  "likelyQuoteRange": {
    "basis": "actual_informed_history",
    "low": 214000,
    "median": 237500,
    "high": 268000,
    "recommendedMedian": 244625,
    "confidence": "high"
  },
  "monthlyRevenueSpread": [
    { "month": "2026-05", "medianSharePct": 18, "spreadProfile": "episodic" },
    { "month": "2026-06", "medianSharePct": 24, "spreadProfile": "episodic" },
    { "month": "2026-07", "medianSharePct": 31, "spreadProfile": "episodic" },
    { "month": "2026-08", "medianSharePct": 27, "spreadProfile": "episodic" }
  ],
  "disciplineUsageHighlights": [
    {
      "disciplineCode": "localisation",
      "predictedAmountMedian": 128000,
      "predictedActualAmount": 136960,
      "predictedVariancePct": 7,
      "overrunRisk": "medium"
    },
    {
      "disciplineCode": "qc",
      "predictedAmountMedian": 46200,
      "predictedActualAmount": 49434,
      "predictedVariancePct": 7,
      "overrunRisk": "medium"
    }
  ],
  "riskFlags": [
    "historical_overrun_pattern",
    "schedule_compression"
  ]
}
```

## 3. In-Flight Finishing Project With Partial Actuals

- Maturity stage: `stage_4`
- Evidence source: `partial_actuals`
- Fallback tier: `in_flight_actuals`

```json
{
  "likelyQuoteRange": {
    "basis": "actual_informed_history",
    "low": 178000,
    "median": 191000,
    "high": 208500,
    "recommendedMedian": 191000,
    "confidence": "high"
  },
  "winProbability": {
    "probabilityPct": 100,
    "probabilityBand": "high",
    "confidence": "high"
  },
  "disciplineUsageHighlights": [
    {
      "disciplineCode": "online",
      "predictedActualAmount": 88250,
      "predictedVariancePct": 11,
      "overrunRisk": "high",
      "keyDrivers": [
        "Stage actuals already posted at 62100.00.",
        "Usage rate 95.0% in comparable work."
      ]
    },
    {
      "disciplineCode": "sound",
      "predictedActualAmount": 31600,
      "predictedVariancePct": 5,
      "overrunRisk": "medium"
    }
  ],
  "scenarioSummary": {
    "base": { "projectedWeightedRevenue": 191000 },
    "upside": { "projectedWeightedRevenue": 205370 },
    "downside": { "projectedWeightedRevenue": 176820 }
  },
  "riskFlags": [
    "historical_overrun_pattern",
    "high_third_party_exposure",
    "in_flight_actuals_present"
  ]
}
```
