import type {
  ActualInformedRange,
  ComparableFactorKey,
  ComparableFactorMatch,
  ComparableProjectScore,
  ComparableProjectSnapshot,
  ComparableRange,
  ComparableRecommendationResult,
  ComparableSelectionResult,
  ComparableSelectionState,
  ComparableStrength,
  DisciplineRecommendationRange,
  RankedComparableProject,
  RiskSignal
} from "./types.js";

const SCORING_MODEL_VERSION = "comparable-project-v1";

const FACTOR_WEIGHTS: Record<ComparableFactorKey, number> = {
  project_format_key: 18,
  client: 15,
  discipline_overlap: 14,
  budget_band: 14,
  schedule_length: 10,
  deliverables_overlap: 8,
  complexity_profile: 8,
  language_localization_profile: 5,
  episode_count: 4,
  counterparty_overlap: 4
};

const COMPLEXITY_LEVELS = new Map<string, number>([
  ["simple", 1],
  ["low", 1],
  ["standard", 2],
  ["medium", 2],
  ["complex", 3],
  ["high", 3]
]);

interface FactorComputation {
  awardedPoints: number;
  detail: string;
  isAvailable: boolean;
}

interface ComputedFactor {
  match: ComparableFactorMatch;
  isAvailable: boolean;
}

interface WeightedValue {
  projectId: string;
  value: number;
  weight: number;
}

function round(value: number): number {
  return Number(value.toFixed(2));
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values.filter((value) => value.length > 0))];
}

function calculateOverlapScore(left: string[], right: string[]): number {
  const leftSet = new Set(uniqueStrings(left));
  const rightSet = new Set(uniqueStrings(right));
  const union = new Set([...leftSet, ...rightSet]);

  if (union.size === 0) {
    return 0;
  }

  let intersectionCount = 0;
  leftSet.forEach((value) => {
    if (rightSet.has(value)) {
      intersectionCount += 1;
    }
  });

  return intersectionCount / union.size;
}

function buildFactorMatch(
  factorKey: ComparableFactorKey,
  label: string,
  computation: FactorComputation
): ComputedFactor {
  return {
    isAvailable: computation.isAvailable,
    match: {
      factorKey,
      label,
      weight: FACTOR_WEIGHTS[factorKey],
      awardedPoints: round(computation.awardedPoints),
      detail: computation.detail
    }
  };
}

function compareExact(
  label: string,
  factorKey: ComparableFactorKey,
  targetValue?: string,
  candidateValue?: string
): ComparableFactorMatch {
  const weight = FACTOR_WEIGHTS[factorKey];

  if (!targetValue || !candidateValue) {
    return buildFactorMatch(factorKey, label, {
      awardedPoints: 0,
      detail: `${label} metadata is missing on the target or candidate project.`,
      isAvailable: false
    }).match;
  }

  if (targetValue === candidateValue) {
    return buildFactorMatch(factorKey, label, {
      awardedPoints: weight,
      detail: `${label} matches exactly.`,
      isAvailable: true
    }).match;
  }

  return buildFactorMatch(factorKey, label, {
    awardedPoints: 0,
    detail: `${label} does not match.`,
    isAvailable: true
  }).match;
}

function compareOverlap(
  label: string,
  factorKey: ComparableFactorKey,
  targetValues: string[],
  candidateValues: string[]
): ComparableFactorMatch {
  const normalizedTarget = uniqueStrings(targetValues);
  const normalizedCandidate = uniqueStrings(candidateValues);

  if (normalizedTarget.length === 0 || normalizedCandidate.length === 0) {
    return buildFactorMatch(factorKey, label, {
      awardedPoints: 0,
      detail: `${label} metadata is missing on the target or candidate project.`,
      isAvailable: false
    }).match;
  }

  const overlap = calculateOverlapScore(normalizedTarget, normalizedCandidate);

  return buildFactorMatch(factorKey, label, {
    awardedPoints: FACTOR_WEIGHTS[factorKey] * overlap,
    detail: `${label} overlap is ${Math.round(overlap * 100)}%.`,
    isAvailable: true
  }).match;
}

function compareBudget(
  targetAmount?: number,
  candidateAmount?: number
): ComparableFactorMatch {
  const factorKey = "budget_band";
  const weight = FACTOR_WEIGHTS[factorKey];

  if (!targetAmount || !candidateAmount || targetAmount <= 0 || candidateAmount <= 0) {
    return buildFactorMatch(factorKey, "Budget Band", {
      awardedPoints: 0,
      detail: "Budget or quote-size metadata is missing on the target or candidate project.",
      isAvailable: false
    }).match;
  }

  const ratio = Math.abs(candidateAmount - targetAmount) / targetAmount;

  if (ratio <= 0.1) {
    return buildFactorMatch(factorKey, "Budget Band", {
      awardedPoints: weight,
      detail: "Budget is within 10% of the target project.",
      isAvailable: true
    }).match;
  }

  if (ratio <= 0.25) {
    return buildFactorMatch(factorKey, "Budget Band", {
      awardedPoints: weight * 0.7,
      detail: "Budget is within 25% of the target project.",
      isAvailable: true
    }).match;
  }

  if (ratio <= 0.5) {
    return buildFactorMatch(factorKey, "Budget Band", {
      awardedPoints: weight * 0.4,
      detail: "Budget is within 50% of the target project.",
      isAvailable: true
    }).match;
  }

  return buildFactorMatch(factorKey, "Budget Band", {
    awardedPoints: 0,
    detail: "Budget is outside the comparable range for the target project.",
    isAvailable: true
  }).match;
}

function compareDuration(
  targetDuration?: number,
  candidateDuration?: number
): ComparableFactorMatch {
  const factorKey = "schedule_length";
  const weight = FACTOR_WEIGHTS[factorKey];

  if (!targetDuration || !candidateDuration || targetDuration <= 0 || candidateDuration <= 0) {
    return buildFactorMatch(factorKey, "Schedule Length", {
      awardedPoints: 0,
      detail: "Schedule-length metadata is missing on the target or candidate project.",
      isAvailable: false
    }).match;
  }

  const difference = Math.abs(candidateDuration - targetDuration);
  const ratio = difference / targetDuration;

  if (difference <= 1 || ratio <= 0.1) {
    return buildFactorMatch(factorKey, "Schedule Length", {
      awardedPoints: weight,
      detail: "Duration is within one week or 10% of the target project.",
      isAvailable: true
    }).match;
  }

  if (ratio <= 0.25) {
    return buildFactorMatch(factorKey, "Schedule Length", {
      awardedPoints: weight * 0.5,
      detail: "Duration is within 25% of the target project.",
      isAvailable: true
    }).match;
  }

  return buildFactorMatch(factorKey, "Schedule Length", {
    awardedPoints: 0,
    detail: "Schedule length is materially different from the target project.",
    isAvailable: true
  }).match;
}

function compareEpisodeCount(
  targetEpisodeCount?: number,
  candidateEpisodeCount?: number
): ComparableFactorMatch {
  const factorKey = "episode_count";
  const weight = FACTOR_WEIGHTS[factorKey];

  if (!targetEpisodeCount || !candidateEpisodeCount) {
    return buildFactorMatch(factorKey, "Episode Count", {
      awardedPoints: 0,
      detail: "Episode-count metadata is missing on the target or candidate project.",
      isAvailable: false
    }).match;
  }

  if (targetEpisodeCount === candidateEpisodeCount) {
    return buildFactorMatch(factorKey, "Episode Count", {
      awardedPoints: weight,
      detail: "Episode count matches exactly.",
      isAvailable: true
    }).match;
  }

  if (Math.abs(targetEpisodeCount - candidateEpisodeCount) <= 1) {
    return buildFactorMatch(factorKey, "Episode Count", {
      awardedPoints: weight * 0.5,
      detail: "Episode count is within one episode of the target project.",
      isAvailable: true
    }).match;
  }

  return buildFactorMatch(factorKey, "Episode Count", {
    awardedPoints: 0,
    detail: "Episode count is outside the comparable range for the target project.",
    isAvailable: true
  }).match;
}

function resolveComplexityValue(value?: string): number | undefined {
  if (!value) {
    return undefined;
  }

  return COMPLEXITY_LEVELS.get(value.toLowerCase());
}

function compareComplexity(
  target: ComparableProjectSnapshot,
  candidate: ComparableProjectSnapshot
): ComparableFactorMatch {
  const factorKey = "complexity_profile";
  const weight = FACTOR_WEIGHTS[factorKey];
  const axes = [
    ["finishing", target.complexityProfile?.finishing, candidate.complexityProfile?.finishing],
    ["audio", target.complexityProfile?.audio, candidate.complexityProfile?.audio],
    ["vfx", target.complexityProfile?.vfx, candidate.complexityProfile?.vfx]
  ] as const;

  const axisScores: number[] = [];

  axes.forEach(([, targetValue, candidateValue]) => {
    const resolvedTarget = resolveComplexityValue(targetValue);
    const resolvedCandidate = resolveComplexityValue(candidateValue);

    if (resolvedTarget === undefined || resolvedCandidate === undefined) {
      return;
    }

    const difference = Math.abs(resolvedTarget - resolvedCandidate);

    if (difference === 0) {
      axisScores.push(1);
      return;
    }

    if (difference === 1) {
      axisScores.push(0.5);
      return;
    }

    axisScores.push(0);
  });

  if (axisScores.length === 0) {
    return buildFactorMatch(factorKey, "Complexity Profile", {
      awardedPoints: 0,
      detail: "Complexity metadata is missing on the target or candidate project.",
      isAvailable: false
    }).match;
  }

  const score = axisScores.reduce((sum, value) => sum + value, 0) / axisScores.length;

  return buildFactorMatch(factorKey, "Complexity Profile", {
    awardedPoints: weight * score,
    detail: `Complexity profile alignment is ${Math.round(score * 100)}% across finishing, audio, and VFX.`,
    isAvailable: true
  }).match;
}

function compareLanguageAndLocalization(
  target: ComparableProjectSnapshot,
  candidate: ComparableProjectSnapshot
): ComparableFactorMatch {
  const factorKey = "language_localization_profile";
  const weight = FACTOR_WEIGHTS[factorKey];
  const targetLanguage = target.primaryLanguageCode;
  const candidateLanguage = candidate.primaryLanguageCode;
  const targetLocalizationKeys = uniqueStrings(target.localizationKeys);
  const candidateLocalizationKeys = uniqueStrings(candidate.localizationKeys);

  const languageAvailable = Boolean(targetLanguage && candidateLanguage);
  const localizationAvailable =
    targetLocalizationKeys.length > 0 && candidateLocalizationKeys.length > 0;

  if (!languageAvailable && !localizationAvailable) {
    return buildFactorMatch(factorKey, "Language / Localization", {
      awardedPoints: 0,
      detail: "Language or localization metadata is missing on the target or candidate project.",
      isAvailable: false
    }).match;
  }

  const languageScore = languageAvailable && targetLanguage === candidateLanguage ? 1 : 0;
  const localizationScore = localizationAvailable
    ? calculateOverlapScore(targetLocalizationKeys, candidateLocalizationKeys)
    : 0;
  const normalizedScore =
    (languageAvailable ? languageScore * 0.6 : 0) +
    (localizationAvailable ? localizationScore * 0.4 : 0);

  return buildFactorMatch(factorKey, "Language / Localization", {
    awardedPoints: weight * normalizedScore,
    detail: `Primary language ${
      languageScore === 1 ? "matches" : "does not match"
    } and localization overlap is ${Math.round(localizationScore * 100)}%.`,
    isAvailable: true
  }).match;
}

function flattenCounterparties(snapshot: ComparableProjectSnapshot): string[] {
  const entries = snapshot.counterpartyCompanyIdsByRole ?? {};

  return uniqueStrings(
    Object.entries(entries).flatMap(([role, companyIds]) => {
      return (companyIds ?? []).map((companyId) => `${role}:${companyId}`);
    })
  );
}

function compareCounterparties(
  target: ComparableProjectSnapshot,
  candidate: ComparableProjectSnapshot
): ComparableFactorMatch {
  return compareOverlap(
    "Counterparty Overlap",
    "counterparty_overlap",
    flattenCounterparties(target),
    flattenCounterparties(candidate)
  );
}

function computeStrength(score: number): ComparableStrength {
  if (score >= 70) {
    return "strong";
  }

  if (score >= 55) {
    return "usable";
  }

  return "weak";
}

function computeProjectFactors(
  target: ComparableProjectSnapshot,
  candidate: ComparableProjectSnapshot
): ComputedFactor[] {
  return [
    buildFactorMatch("project_format_key", "Project Format", {
      awardedPoints: compareExact(
        "Project Format",
        "project_format_key",
        target.projectFormatKey,
        candidate.projectFormatKey
      ).awardedPoints,
      detail: compareExact(
        "Project Format",
        "project_format_key",
        target.projectFormatKey,
        candidate.projectFormatKey
      ).detail,
      isAvailable: Boolean(target.projectFormatKey && candidate.projectFormatKey)
    }),
    buildFactorMatch("client", "Client", {
      awardedPoints: compareExact("Client", "client", target.clientId, candidate.clientId)
        .awardedPoints,
      detail: compareExact("Client", "client", target.clientId, candidate.clientId).detail,
      isAvailable: Boolean(target.clientId && candidate.clientId)
    }),
    buildFactorMatch("discipline_overlap", "Discipline Overlap", {
      awardedPoints: compareOverlap(
        "Discipline Overlap",
        "discipline_overlap",
        target.disciplineIds,
        candidate.disciplineIds
      ).awardedPoints,
      detail: compareOverlap(
        "Discipline Overlap",
        "discipline_overlap",
        target.disciplineIds,
        candidate.disciplineIds
      ).detail,
      isAvailable: target.disciplineIds.length > 0 && candidate.disciplineIds.length > 0
    }),
    buildFactorMatch("budget_band", "Budget Band", {
      awardedPoints: compareBudget(target.targetAmount, candidate.targetAmount).awardedPoints,
      detail: compareBudget(target.targetAmount, candidate.targetAmount).detail,
      isAvailable: Boolean(target.targetAmount && candidate.targetAmount)
    }),
    buildFactorMatch("schedule_length", "Schedule Length", {
      awardedPoints: compareDuration(target.durationWeeks, candidate.durationWeeks).awardedPoints,
      detail: compareDuration(target.durationWeeks, candidate.durationWeeks).detail,
      isAvailable: Boolean(target.durationWeeks && candidate.durationWeeks)
    }),
    buildFactorMatch("deliverables_overlap", "Deliverables Overlap", {
      awardedPoints: compareOverlap(
        "Deliverables Overlap",
        "deliverables_overlap",
        target.deliverableKeys,
        candidate.deliverableKeys
      ).awardedPoints,
      detail: compareOverlap(
        "Deliverables Overlap",
        "deliverables_overlap",
        target.deliverableKeys,
        candidate.deliverableKeys
      ).detail,
      isAvailable: target.deliverableKeys.length > 0 && candidate.deliverableKeys.length > 0
    }),
    buildFactorMatch("complexity_profile", "Complexity Profile", {
      awardedPoints: compareComplexity(target, candidate).awardedPoints,
      detail: compareComplexity(target, candidate).detail,
      isAvailable:
        Boolean(target.complexityProfile?.finishing || target.complexityProfile?.audio || target.complexityProfile?.vfx) &&
        Boolean(
          candidate.complexityProfile?.finishing ||
            candidate.complexityProfile?.audio ||
            candidate.complexityProfile?.vfx
        )
    }),
    buildFactorMatch("language_localization_profile", "Language / Localization", {
      awardedPoints: compareLanguageAndLocalization(target, candidate).awardedPoints,
      detail: compareLanguageAndLocalization(target, candidate).detail,
      isAvailable:
        Boolean(target.primaryLanguageCode && candidate.primaryLanguageCode) ||
        (target.localizationKeys.length > 0 && candidate.localizationKeys.length > 0)
    }),
    buildFactorMatch("episode_count", "Episode Count", {
      awardedPoints: compareEpisodeCount(target.episodeCount, candidate.episodeCount).awardedPoints,
      detail: compareEpisodeCount(target.episodeCount, candidate.episodeCount).detail,
      isAvailable: Boolean(target.episodeCount && candidate.episodeCount)
    }),
    buildFactorMatch("counterparty_overlap", "Counterparty Overlap", {
      awardedPoints: compareCounterparties(target, candidate).awardedPoints,
      detail: compareCounterparties(target, candidate).detail,
      isAvailable:
        flattenCounterparties(target).length > 0 && flattenCounterparties(candidate).length > 0
    })
  ].sort((left, right) => right.match.awardedPoints - left.match.awardedPoints);
}

export function scoreComparableProject(
  target: ComparableProjectSnapshot,
  candidate: ComparableProjectSnapshot
): ComparableProjectScore {
  const computedFactors = computeProjectFactors(target, candidate);
  const achievedPoints = computedFactors.reduce((sum, factor) => {
    return sum + factor.match.awardedPoints;
  }, 0);
  const availableWeight = computedFactors.reduce((sum, factor) => {
    return sum + (factor.isAvailable ? factor.match.weight : 0);
  }, 0);

  return {
    similarityScore: round(Math.min(100, achievedPoints)),
    coveragePct: round((availableWeight / 100) * 100),
    strength: computeStrength(achievedPoints),
    matchedFactors: computedFactors.map((factor) => factor.match)
  };
}

function isRecommendationEligible(
  target: ComparableProjectSnapshot,
  candidate: ComparableProjectSnapshot,
  selectionState: ComparableSelectionState,
  score: ComparableProjectScore
): boolean {
  if (selectionState === "excluded") {
    return false;
  }

  if (score.strength === "weak") {
    return false;
  }

  if (target.quoteCurrencyCode !== candidate.quoteCurrencyCode) {
    return false;
  }

  if (!["awarded", "complete"].includes(candidate.status)) {
    return false;
  }

  return Boolean(candidate.benchmarkSummary?.quotedAmount);
}

function collectTargetRiskSignals(target: ComparableProjectSnapshot): RiskSignal[] {
  const signals: RiskSignal[] = [];

  if (!target.projectFormatKey) {
    signals.push({
      key: "missing_project_format",
      severity: "warning",
      detail: "Target project is missing a controlled project format key."
    });
  }

  if (!target.primaryLanguageCode) {
    signals.push({
      key: "missing_primary_language",
      severity: "info",
      detail: "Target project is missing a primary language code."
    });
  }

  if (target.deliverableKeys.length === 0) {
    signals.push({
      key: "missing_deliverables",
      severity: "info",
      detail: "Target project has no structured deliverable metadata."
    });
  }

  if (
    !target.complexityProfile?.finishing &&
    !target.complexityProfile?.audio &&
    !target.complexityProfile?.vfx
  ) {
    signals.push({
      key: "missing_complexity_profile",
      severity: "info",
      detail: "Target project is missing structured complexity metadata."
    });
  }

  return signals;
}

export function rankComparableProjects(input: {
  target: ComparableProjectSnapshot;
  candidates: ComparableProjectSnapshot[];
  pinnedProjectIds?: string[];
  excludedProjectIds?: string[];
  limit?: number;
  disciplineId?: string;
}): ComparableSelectionResult {
  const pinnedProjectIds = new Set(input.pinnedProjectIds ?? []);
  const excludedProjectIds = new Set(input.excludedProjectIds ?? []);
  const items: RankedComparableProject[] = [];
  const riskSignals = collectTargetRiskSignals(input.target);
  let currencyFilteredCandidateCount = 0;

  input.candidates.forEach((candidate) => {
    if (candidate.id === input.target.id) {
      return;
    }

    const disciplineMatch = input.disciplineId
      ? candidate.disciplineIds.includes(input.disciplineId)
      : true;

    if (!disciplineMatch) {
      return;
    }

    const score = scoreComparableProject(input.target, candidate);
    const selectionState: ComparableSelectionState = excludedProjectIds.has(candidate.id)
      ? "excluded"
      : pinnedProjectIds.has(candidate.id)
        ? "pinned"
        : "auto";

    if (
      selectionState === "auto" &&
      score.strength === "weak"
    ) {
      return;
    }

    if (candidate.quoteCurrencyCode !== input.target.quoteCurrencyCode) {
      currencyFilteredCandidateCount += 1;
    }

    items.push({
      project: candidate,
      score,
      selectionState,
      isEligibleForRecommendations: isRecommendationEligible(
        input.target,
        candidate,
        selectionState,
        score
      )
    });
  });

  const sortedItems = items
    .sort((left, right) => {
      const selectionPriority = {
        pinned: 0,
        auto: 1,
        excluded: 2
      };
      const selectionDifference =
        selectionPriority[left.selectionState] - selectionPriority[right.selectionState];

      if (selectionDifference !== 0) {
        return selectionDifference;
      }

      if (right.score.similarityScore !== left.score.similarityScore) {
        return right.score.similarityScore - left.score.similarityScore;
      }

      return right.score.coveragePct - left.score.coveragePct;
    })
    .slice(0, input.limit ?? 10);

  if (currencyFilteredCandidateCount > 0) {
    riskSignals.push({
      key: "currency_filtered_candidates",
      severity: "info",
      detail: `${currencyFilteredCandidateCount} candidate project(s) were ignored because their quote currency did not match the target project.`
    });
  }

  return {
    items: sortedItems,
    riskSignals
  };
}

function buildWeightedRange(
  values: WeightedValue[],
  currencyCode: string
): ComparableRange | null {
  if (values.length < 3) {
    return null;
  }

  if (values.length < 5) {
    const sortedByValue = values.slice().sort((left, right) => left.value - right.value);

    return {
      low: round(sortedByValue[0]!.value),
      median: weightedPercentile(values, 0.5),
      high: round(sortedByValue[sortedByValue.length - 1]!.value),
      currencyCode,
      sampleSize: values.length,
      comparableProjectIds: values.map((value) => value.projectId),
      methodology: "min_median_max"
    };
  }

  return {
    low: weightedPercentile(values, 0.25),
    median: weightedPercentile(values, 0.5),
    high: weightedPercentile(values, 0.75),
    currencyCode,
    sampleSize: values.length,
    comparableProjectIds: values.map((value) => value.projectId),
    methodology: "weighted_percentiles"
  };
}

function weightedPercentile(values: WeightedValue[], percentile: number): number {
  const totalWeight = values.reduce((sum, value) => sum + value.weight, 0);
  const targetWeight = totalWeight * percentile;
  const sortedValues = values.slice().sort((left, right) => left.value - right.value);

  let cumulativeWeight = 0;

  for (const value of sortedValues) {
    cumulativeWeight += value.weight;

    if (cumulativeWeight >= targetWeight) {
      return round(value.value);
    }
  }

  return round(sortedValues[sortedValues.length - 1]!.value);
}

function buildActualInformedRange(
  quoteRange: ComparableRange | null,
  values: WeightedValue[],
  currencyCode: string
): ActualInformedRange | null {
  if (!quoteRange || values.length < 3) {
    return null;
  }

  const ratioRange = buildWeightedRange(values, currencyCode);

  if (!ratioRange) {
    return null;
  }

  return {
    low: round(quoteRange.low * (1 + ratioRange.low / 100)),
    median: round(quoteRange.median * (1 + ratioRange.median / 100)),
    high: round(quoteRange.high * (1 + ratioRange.high / 100)),
    currencyCode,
    sampleSize: ratioRange.sampleSize,
    comparableProjectIds: ratioRange.comparableProjectIds,
    methodology: ratioRange.methodology,
    varianceLowPct: ratioRange.low,
    varianceMedianPct: ratioRange.median,
    varianceHighPct: ratioRange.high
  };
}

function buildDisciplineRanges(
  rankedComparables: RankedComparableProject[],
  currencyCode: string,
  disciplineId?: string
): DisciplineRecommendationRange[] {
  type DisciplineAccumulator = {
    disciplineName: string | undefined;
    quoted: WeightedValue[];
    variance: WeightedValue[];
  };

  const valuesByDiscipline = new Map<
    string,
    DisciplineAccumulator
  >();

  rankedComparables.forEach((item) => {
    if (!item.isEligibleForRecommendations) {
      return;
    }

    item.project.benchmarkSummary?.disciplineSummaries.forEach((summary) => {
      if (disciplineId && summary.disciplineId !== disciplineId) {
        return;
      }

      const current: DisciplineAccumulator = valuesByDiscipline.get(summary.disciplineId) ?? {
        disciplineName: undefined,
        quoted: [] as WeightedValue[],
        variance: [] as WeightedValue[]
      };

      if (summary.disciplineName && !current.disciplineName) {
        current.disciplineName = summary.disciplineName;
      }

      current.quoted.push({
        projectId: item.project.id,
        value: summary.quotedAmount,
        weight: item.score.similarityScore
      });

      if (
        summary.actualsStatus === "complete" &&
        summary.quoteToActualVariancePct !== undefined
      ) {
        current.variance.push({
          projectId: item.project.id,
          value: summary.quoteToActualVariancePct,
          weight: item.score.similarityScore
        });
      }

      valuesByDiscipline.set(summary.disciplineId, current);
    });
  });

  return [...valuesByDiscipline.entries()]
    .map(([currentDisciplineId, values]) => {
      const quotedRange = buildWeightedRange(values.quoted, currencyCode);

      if (!quotedRange) {
        return null;
      }

      const varianceMedian =
        values.variance.length >= 3 ? weightedPercentile(values.variance, 0.5) : undefined;

      const disciplineRange: DisciplineRecommendationRange = {
        disciplineId: currentDisciplineId,
        low: quotedRange.low,
        median: quotedRange.median,
        high: quotedRange.high,
        currencyCode: quotedRange.currencyCode,
        sampleSize: quotedRange.sampleSize,
        comparableProjectIds: quotedRange.comparableProjectIds,
        methodology: quotedRange.methodology
      };

      if (values.disciplineName) {
        disciplineRange.disciplineName = values.disciplineName;
      }

      if (varianceMedian !== undefined) {
        disciplineRange.observedVarianceMedianPct = varianceMedian;
      }

      return disciplineRange;
    })
    .filter((value): value is DisciplineRecommendationRange => value !== null)
    .sort((left, right) => right.sampleSize - left.sampleSize);
}

export function buildComparableRecommendations(input: {
  target: ComparableProjectSnapshot;
  candidates: ComparableProjectSnapshot[];
  pinnedProjectIds?: string[];
  excludedProjectIds?: string[];
  limit?: number;
  disciplineId?: string;
}): ComparableRecommendationResult {
  const selection = rankComparableProjects(input);
  const recommendationCandidates = selection.items.filter((item) => {
    return item.isEligibleForRecommendations;
  });
  const overallQuotedValues: WeightedValue[] = recommendationCandidates.map((item) => ({
    projectId: item.project.id,
    value: item.project.benchmarkSummary!.quotedAmount,
    weight: item.score.similarityScore
  }));
  const overallQuoteRange = buildWeightedRange(
    overallQuotedValues,
    input.target.quoteCurrencyCode
  );
  const overallActualVarianceValues: WeightedValue[] = recommendationCandidates
    .filter((item) => {
      return (
        item.project.status === "complete" &&
        item.project.benchmarkSummary?.actualsStatus === "complete" &&
        item.project.benchmarkSummary.quoteToActualVariancePct !== undefined
      );
    })
    .map((item) => ({
      projectId: item.project.id,
      value: item.project.benchmarkSummary!.quoteToActualVariancePct!,
      weight: item.score.similarityScore
    }));
  const overallActualInformedRange = buildActualInformedRange(
    overallQuoteRange,
    overallActualVarianceValues,
    input.target.quoteCurrencyCode
  );
  const riskSignals = [...selection.riskSignals];

  if (recommendationCandidates.length < 3) {
    riskSignals.push({
      key: "insufficient_comparables",
      severity: "warning",
      detail:
        "Fewer than three eligible awarded or complete projects were available, so numeric recommendations were suppressed."
    });
  }

  if (overallActualVarianceValues.length < 3) {
    riskSignals.push({
      key: "insufficient_actuals_history",
      severity: "info",
      detail:
        "Fewer than three complete projects had trustworthy actuals, so actual-informed guidance is limited."
    });
  }

  return {
    overallQuoteRange,
    overallActualInformedRange,
    disciplineRanges: buildDisciplineRanges(
      recommendationCandidates,
      input.target.quoteCurrencyCode,
      input.disciplineId
    ),
    comparablesUsed: recommendationCandidates.map((item) => item.project.id),
    riskSignals,
    methodologySummary:
      "Quotes use weighted comparable ranges from issued won work. Actual-informed guidance only uses complete projects with approved actuals.",
    rankedComparables: selection.items
  };
}

export function getComparableScoringModelVersion(): string {
  return SCORING_MODEL_VERSION;
}
