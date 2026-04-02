export const PREDICTED_SPEND_FALLBACK_TIERS = [
  "none",
  "discipline_history_only",
  "project_type_history_only",
  "global_history_only",
  "manual_placeholder",
] as const;

export type PredictedSpendFallbackTier =
  (typeof PREDICTED_SPEND_FALLBACK_TIERS)[number];

export const PREDICTED_SPEND_VARIANCE_RISKS = ["low", "medium", "high"] as const;

export type PredictedSpendVarianceRisk =
  (typeof PREDICTED_SPEND_VARIANCE_RISKS)[number];

export const PREDICTED_SPEND_ADVISORY_STATES = [
  "loading",
  "no_prediction_available",
  "sparse_data_low_confidence",
  "stale_prediction",
  "active",
  "overridden",
  "ignored",
] as const;

export type PredictedSpendAdvisoryState =
  (typeof PREDICTED_SPEND_ADVISORY_STATES)[number];

export interface ComparableProjectRef {
  project_id: string;
  similarity_score: number;
  rationale: string;
}

export interface ProjectLevelPredictedSpend {
  project_id: string;
  predicted_spend_low: number;
  predicted_spend_expected: number;
  predicted_spend_high: number;
  confidence_score: number;
  data_sufficiency_score: number;
  fallback_tier: PredictedSpendFallbackTier;
  explanation_summary: string;
  comparable_project_refs: ComparableProjectRef[];
  prediction_timestamp: string;
  prediction_version: string;
}

export interface DisciplineLevelPredictedSpend {
  project_id: string;
  discipline: string;
  predicted_spend_low: number;
  predicted_spend_expected: number;
  predicted_spend_high: number;
  confidence_score: number;
  main_drivers: string[];
  variance_risk: PredictedSpendVarianceRisk;
}

export interface QuoteVsPredictedDisciplineRow {
  discipline: string;
  quoted_amount: number;
  predicted_spend_expected: number;
  quoted_vs_predicted_gap: number;
  quoted_vs_predicted_gap_pct: number;
  variance_risk: PredictedSpendVarianceRisk;
}

export interface QuoteComparisonView {
  quoted_total: number;
  predicted_spend_total: number;
  quoted_vs_predicted_gap: number;
  discipline_comparison_rows: QuoteVsPredictedDisciplineRow[];
}

export interface AdvisoryUiState {
  state: PredictedSpendAdvisoryState;
  reason_code: string;
  message: string;
  stale_after_hours: number;
  advisory_acted_by_user_id?: string | null;
  advisory_acted_at?: string | null;
}

export interface PredictedSpendAdvisoryContract {
  project_level_predicted_spend: ProjectLevelPredictedSpend;
  discipline_level_predicted_spend: DisciplineLevelPredictedSpend[];
  quote_comparison_view: QuoteComparisonView;
  advisory_ui_state: AdvisoryUiState;
}

export interface PredictedSpendValidationError {
  field: string;
  issue: string;
}

export function validatePredictedSpendContract(
  payload: PredictedSpendAdvisoryContract,
): PredictedSpendValidationError[] {
  const errors: PredictedSpendValidationError[] = [];

  const project = payload.project_level_predicted_spend;
  const low = project.predicted_spend_low;
  const expected = project.predicted_spend_expected;
  const high = project.predicted_spend_high;

  if (!(low <= expected && expected <= high)) {
    errors.push({
      field: "project_level_predicted_spend",
      issue: "predicted_spend_low <= predicted_spend_expected <= predicted_spend_high is required.",
    });
  }

  if (project.confidence_score < 0 || project.confidence_score > 1) {
    errors.push({
      field: "project_level_predicted_spend.confidence_score",
      issue: "confidence_score must be between 0 and 1.",
    });
  }

  if (project.data_sufficiency_score < 0 || project.data_sufficiency_score > 1) {
    errors.push({
      field: "project_level_predicted_spend.data_sufficiency_score",
      issue: "data_sufficiency_score must be between 0 and 1.",
    });
  }

  for (const row of payload.discipline_level_predicted_spend) {
    if (!(row.predicted_spend_low <= row.predicted_spend_expected && row.predicted_spend_expected <= row.predicted_spend_high)) {
      errors.push({
        field: `discipline_level_predicted_spend.${row.discipline}`,
        issue: "predicted_spend_low <= predicted_spend_expected <= predicted_spend_high is required.",
      });
    }

    if (row.confidence_score < 0 || row.confidence_score > 1) {
      errors.push({
        field: `discipline_level_predicted_spend.${row.discipline}.confidence_score`,
        issue: "confidence_score must be between 0 and 1.",
      });
    }
  }

  return errors;
}

export interface RevenueForecastSeparationViolation {
  field: string;
  issue: string;
}

export function validatePredictedSpendRevenueSeparation(
  payload: PredictedSpendAdvisoryContract,
): RevenueForecastSeparationViolation[] {
  const violations: RevenueForecastSeparationViolation[] = [];

  const forbiddenTokens = [
    "forecast",
    "forecast_version",
    "monthly_revenue",
    "weighted_revenue",
    "quote_version",
  ];

  const serialized = JSON.stringify(payload).toLowerCase();
  for (const token of forbiddenTokens) {
    if (serialized.includes(token)) {
      violations.push({
        field: "payload",
        issue: `Predicted spend advisory payload must not include revenue forecast field '${token}'.`,
      });
    }
  }

  return violations;
}
