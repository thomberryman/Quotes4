export const USER_ROLE_KEYS = [
  "system_admin",
  "sales_estimator",
  "post_producer",
  "post_supervisor",
  "finance_analyst",
  "leadership_read_only"
] as const;

export type UserRoleKey = (typeof USER_ROLE_KEYS)[number];

export const PROJECT_STATUSES = [
  "bid",
  "awarded",
  "lost",
  "active",
  "complete",
  "archived"
] as const;

export type ProjectStatus = (typeof PROJECT_STATUSES)[number];

export const QUOTE_VERSION_STATUSES = [
  "draft",
  "issued",
  "superseded",
  "accepted",
  "rejected"
] as const;

export type QuoteVersionStatus = (typeof QUOTE_VERSION_STATUSES)[number];

export const FORECAST_ALLOCATION_METHODS = ["schedule", "manual"] as const;

export type ForecastAllocationMethod =
  (typeof FORECAST_ALLOCATION_METHODS)[number];

export const FORECAST_OUTCOME_BUCKETS = ["bid", "awarded", "lost"] as const;

export type ForecastOutcomeBucket = (typeof FORECAST_OUTCOME_BUCKETS)[number];

export interface MonthlyAllocation {
  month: string;
  amount: number;
  amountInCents: number;
}

export interface ScheduleAllocationInput {
  startDate: Date | string;
  endDate: Date | string;
  amount: number;
  disciplineId?: string;
  currencyCode: string;
}

export interface ManualAllocationInput {
  expectedAmount: number;
  allocations: Array<{
    month: string;
    amount: number;
  }>;
}

export interface ManualAllocationValidationResult {
  isValid: boolean;
  normalizedAllocations: MonthlyAllocation[];
  totalAmount: number;
  differenceFromExpected: number;
  issues: string[];
}

export interface WeightedMonthlyAllocation extends MonthlyAllocation {
  weightedAmount: number;
  weightedAmountInCents: number;
}

export interface ForecastOutcomeEvent {
  outcomeType: ForecastOutcomeBucket;
  effectiveAt: Date | string;
}

export interface ForecastScheduleRange {
  id: string;
  label: string;
  startDate: Date | string;
  endDate: Date | string;
  disciplineId?: string;
  allocationPercent?: number;
}

export interface ForecastScheduleSlice {
  scheduleRangeId: string;
  scheduleRangeLabel: string;
  startDate: Date | string;
  endDate: Date | string;
  allocationPercent: number;
}

export interface ForecastScheduleResolutionResult {
  isValid: boolean;
  issues: string[];
  slices: ForecastScheduleSlice[];
}

export interface ForecastLineInput {
  id: string;
  label: string;
  totalAmount: number;
  currencyCode: string;
  allocationMethod: ForecastAllocationMethod;
  disciplineId?: string;
  scheduleRangeId?: string;
  allocations?: Array<{
    month: string;
    amount: number;
  }>;
  notes?: string;
}

export interface ForecastLineResult {
  id: string;
  sourceLineId: string;
  label: string;
  totalAmount: number;
  totalAmountInCents: number;
  currencyCode: string;
  allocationMethod: ForecastAllocationMethod;
  disciplineId?: string;
  scheduleRangeId?: string;
  notes?: string;
  issues: string[];
  allocations: WeightedMonthlyAllocation[];
}

export interface ForecastDisciplineMonthlyRollup {
  disciplineId?: string;
  month: string;
  amount: number;
  amountInCents: number;
  weightedAmount: number;
  weightedAmountInCents: number;
}

export interface ForecastProjectMonthlyRollup {
  month: string;
  amount: number;
  amountInCents: number;
  weightedAmount: number;
  weightedAmountInCents: number;
}

export interface ForecastVersionCalculationInput {
  projectStatus: ProjectStatus;
  probabilityPercent?: number;
  outcomes: ForecastOutcomeEvent[];
  scheduleRanges: ForecastScheduleRange[];
  lines: ForecastLineInput[];
}

export interface ForecastVersionCalculationResult {
  outcomeTypeSnapshot: ForecastOutcomeBucket;
  probabilityPercent: number;
  totalAmount: number;
  totalAmountInCents: number;
  weightedTotalAmount: number;
  weightedTotalAmountInCents: number;
  lines: ForecastLineResult[];
  disciplineMonthlyRollups: ForecastDisciplineMonthlyRollup[];
  projectMonthlyRollups: ForecastProjectMonthlyRollup[];
  issues: string[];
}

export interface ManualForecastOverrideInput {
  line: Pick<
    ForecastLineResult,
    "id" | "label" | "totalAmount" | "currencyCode" | "disciplineId" | "notes"
  >;
  allocations: Array<{
    month: string;
    amount: number;
  }>;
  reason?: string;
}

export interface VarianceSummary {
  quotedAmount: number;
  forecastAmount: number;
  actualAmount: number;
  quoteToActualVariance: number;
  forecastToActualVariance: number;
}

export const ACTUALS_STATUSES = ["none", "partial", "complete"] as const;

export type ActualsStatus = (typeof ACTUALS_STATUSES)[number];

export const COMPARABLE_FACTOR_KEYS = [
  "project_format_key",
  "client",
  "discipline_overlap",
  "budget_band",
  "schedule_length",
  "deliverables_overlap",
  "complexity_profile",
  "language_localization_profile",
  "episode_count",
  "counterparty_overlap"
] as const;

export type ComparableFactorKey = (typeof COMPARABLE_FACTOR_KEYS)[number];

export const COMPARABLE_STRENGTHS = ["strong", "usable", "weak"] as const;

export type ComparableStrength = (typeof COMPARABLE_STRENGTHS)[number];

export const COMPARABLE_SELECTION_STATES = ["auto", "pinned", "excluded"] as const;

export type ComparableSelectionState =
  (typeof COMPARABLE_SELECTION_STATES)[number];

export const RISK_SIGNAL_SEVERITIES = ["info", "warning"] as const;

export type RiskSignalSeverity = (typeof RISK_SIGNAL_SEVERITIES)[number];

export const COMPARABLE_COUNTERPARTY_ROLES = [
  "client",
  "production_company",
  "studio",
  "streamer",
  "broadcaster",
  "competitor"
] as const;

export type ComparableCounterpartyRole =
  (typeof COMPARABLE_COUNTERPARTY_ROLES)[number];

export interface ComparableComplexityProfile {
  finishing?: string;
  audio?: string;
  vfx?: string;
}

export interface ComparableBenchmarkDisciplineSummary {
  disciplineId: string;
  disciplineName?: string;
  quotedAmount: number;
  actualAmount?: number;
  quoteToActualVarianceAmount?: number;
  quoteToActualVariancePct?: number;
  actualsStatus: ActualsStatus;
}

export interface ComparableBenchmarkSummary {
  sourceQuoteVersionId?: string;
  currencyCode: string;
  quotedAmount: number;
  actualAmount?: number;
  quoteToActualVarianceAmount?: number;
  quoteToActualVariancePct?: number;
  actualsStatus: ActualsStatus;
  actualsAsOfDate?: string;
  disciplineSummaries: ComparableBenchmarkDisciplineSummary[];
}

export interface ComparableProjectSnapshot {
  id: string;
  projectName?: string;
  status: ProjectStatus;
  clientId?: string;
  clientName?: string;
  projectFormatKey?: string;
  disciplineIds: string[];
  targetAmount?: number;
  durationWeeks?: number;
  episodeCount?: number;
  quoteCurrencyCode: string;
  primaryLanguageCode?: string;
  deliverableKeys: string[];
  localizationKeys: string[];
  complexityProfile?: ComparableComplexityProfile;
  counterpartyCompanyIdsByRole?: Partial<
    Record<ComparableCounterpartyRole, string[]>
  >;
  benchmarkSummary?: ComparableBenchmarkSummary;
}

export interface ComparableFactorMatch {
  factorKey: ComparableFactorKey;
  label: string;
  weight: number;
  awardedPoints: number;
  detail: string;
}

export interface ComparableProjectScore {
  similarityScore: number;
  coveragePct: number;
  strength: ComparableStrength;
  matchedFactors: ComparableFactorMatch[];
}

export interface RiskSignal {
  key: string;
  severity: RiskSignalSeverity;
  detail: string;
}

export interface ComparableRange {
  low: number;
  median: number;
  high: number;
  currencyCode: string;
  sampleSize: number;
  comparableProjectIds: string[];
  methodology: "weighted_percentiles" | "min_median_max";
}

export interface ActualInformedRange extends ComparableRange {
  varianceLowPct: number;
  varianceMedianPct: number;
  varianceHighPct: number;
}

export interface DisciplineRecommendationRange extends ComparableRange {
  disciplineId: string;
  disciplineName?: string;
  observedVarianceMedianPct?: number;
}

export interface RankedComparableProject {
  project: ComparableProjectSnapshot;
  score: ComparableProjectScore;
  selectionState: ComparableSelectionState;
  isEligibleForRecommendations: boolean;
}

export interface ComparableSelectionResult {
  items: RankedComparableProject[];
  riskSignals: RiskSignal[];
}

export interface ComparableRecommendationResult {
  overallQuoteRange: ComparableRange | null;
  overallActualInformedRange: ActualInformedRange | null;
  disciplineRanges: DisciplineRecommendationRange[];
  comparablesUsed: string[];
  riskSignals: RiskSignal[];
  methodologySummary: string;
  rankedComparables: RankedComparableProject[];
}
