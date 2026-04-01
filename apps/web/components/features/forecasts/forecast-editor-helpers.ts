import type {
  ForecastDetailRead,
  ForecastProjectMonthlyRollupRead,
  ForecastSanityCheckRead,
  ForecastVersionRead,
  ForecastVersionSummaryRead,
} from "@quotes4/contracts";

const SCENARIO_ORDER = ["base", "upside", "downside"];
const CONFIDENCE_WARNING_KEYS = new Set([
  "confidence_too_high_for_metadata",
  "narrow_bands_sparse_data",
]);
const SCENARIO_WARNING_KEYS = new Set(["scenario_outputs_too_similar"]);

export type ForecastScenarioOption = {
  scenarioKey: string;
  label: string;
  count: number;
  latestVersionId: string;
  latestVersionNumber: number;
  totalAmount: number;
  weightedTotalAmount: number;
  confidenceScore: number | null;
  status: string;
};

export type ForecastMonthlyComparisonRow = {
  month: string;
  amount: number;
  weightedAmount: number;
  lowAmount: number | null;
  highAmount: number | null;
  actualAmount: number | null;
  comparisonAmount: number | null;
  comparisonWeightedAmount: number | null;
  deltaAmount: number;
};

export type ForecastRollupSummary = {
  lowTotal: number | null;
  highTotal: number | null;
  actualMonthCount: number;
  monthCount: number;
  peakMonth: string | null;
  peakAmount: number;
};

export type ForecastSanitySummary = {
  allChecks: ForecastSanityCheckRead[];
  blockingChecks: ForecastSanityCheckRead[];
  warningChecks: ForecastSanityCheckRead[];
  otherBlockingIssues: string[];
  allBlockingMessages: string[];
  confidenceChecks: ForecastSanityCheckRead[];
  scenarioChecks: ForecastSanityCheckRead[];
  checksByLineId: Record<string, ForecastSanityCheckRead[]>;
  checksByMonth: Record<string, ForecastSanityCheckRead[]>;
  blockingLineIds: string[];
  warningLineIds: string[];
  blockingMonths: string[];
  warningMonths: string[];
  affectedLineCount: number;
  affectedMonthCount: number;
};

function normalizeScenarioKey(value?: string | null): string {
  return value && value.length > 0 ? value : "base";
}

function scenarioSortIndex(value: string): number {
  const index = SCENARIO_ORDER.indexOf(value);
  return index >= 0 ? index : SCENARIO_ORDER.length;
}

function toMonthValue(month: string): number {
  const [yearText, monthText] = month.split("-");
  const year = Number(yearText);
  const monthValue = Number(monthText);

  if (!Number.isFinite(year) || !Number.isFinite(monthValue)) {
    return Number.POSITIVE_INFINITY;
  }

  return year * 100 + monthValue;
}

function sortVersionsDescending(
  left: ForecastVersionSummaryRead,
  right: ForecastVersionSummaryRead,
): number {
  return (
    right.versionNumber - left.versionNumber ||
    new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime()
  );
}

function severityRank(check: ForecastSanityCheckRead): number {
  if (check.blocking || check.severity === "error") {
    return 0;
  }
  if (check.severity === "warning") {
    return 1;
  }
  return 2;
}

function scopeRank(scope: string): number {
  switch (scope) {
    case "detail":
      return 0;
    case "version":
      return 1;
    case "line":
      return 2;
    default:
      return 3;
  }
}

function compareSanityChecks(
  left: ForecastSanityCheckRead,
  right: ForecastSanityCheckRead,
): number {
  return (
    severityRank(left) - severityRank(right) ||
    scopeRank(left.scope) - scopeRank(right.scope) ||
    (left.month ?? "").localeCompare(right.month ?? "") ||
    (left.lineId ?? "").localeCompare(right.lineId ?? "") ||
    left.title.localeCompare(right.title) ||
    left.detail.localeCompare(right.detail)
  );
}

function buildSanityCheckIdentity(check: ForecastSanityCheckRead): string {
  return [
    check.key,
    check.severity,
    check.scope,
    check.lineId ?? "",
    check.month ?? "",
    check.title,
    check.detail,
  ].join("::");
}

function buildBlockingIssueMessage(check: ForecastSanityCheckRead): string {
  return `${check.title}: ${check.detail}`;
}

function uniqueValues(values: string[]): string[] {
  return Array.from(new Set(values.filter((value) => value.length > 0)));
}

function dedupeSanityChecks(
  checks: ForecastSanityCheckRead[],
): ForecastSanityCheckRead[] {
  const seen = new Set<string>();
  return checks
    .filter((check) => {
      const identity = buildSanityCheckIdentity(check);
      if (seen.has(identity)) {
        return false;
      }
      seen.add(identity);
      return true;
    })
    .sort(compareSanityChecks);
}

export function buildForecastScenarioOptions(
  versions: ForecastVersionSummaryRead[],
): ForecastScenarioOption[] {
  const grouped = new Map<string, ForecastVersionSummaryRead[]>();

  versions.forEach((version) => {
    const scenarioKey = normalizeScenarioKey(version.scenarioKey);
    const scenarioVersions = grouped.get(scenarioKey) ?? [];
    scenarioVersions.push(version);
    grouped.set(scenarioKey, scenarioVersions);
  });

  return Array.from(grouped.entries())
    .sort(([leftKey], [rightKey]) => {
      const leftIndex = scenarioSortIndex(leftKey);
      const rightIndex = scenarioSortIndex(rightKey);
      return leftIndex - rightIndex || leftKey.localeCompare(rightKey);
    })
    .map(([scenarioKey, scenarioVersions]) => {
      const latestVersion = scenarioVersions
        .slice()
        .sort(sortVersionsDescending)[0];

      if (!latestVersion) {
        throw new Error(`Scenario ${scenarioKey} has no forecast versions.`);
      }

      return {
        scenarioKey,
        label:
          scenarioKey.charAt(0).toUpperCase() + scenarioKey.slice(1).replace(/_/g, " "),
        count: scenarioVersions.length,
        latestVersionId: latestVersion.id,
        latestVersionNumber: latestVersion.versionNumber,
        totalAmount: latestVersion.totalAmount,
        weightedTotalAmount: latestVersion.weightedTotalAmount,
        confidenceScore: latestVersion.confidenceScore ?? null,
        status: latestVersion.status,
      };
    });
}

export function getDefaultForecastComparisonVersionId(
  selectedVersionId: string,
  selectedVersion: ForecastVersionRead | null | undefined,
  versions: ForecastVersionSummaryRead[],
): string {
  if (
    selectedVersion?.parentVersionId &&
    versions.some((version) => version.id === selectedVersion.parentVersionId)
  ) {
    return selectedVersion.parentVersionId;
  }

  const selectedSummary = versions.find((version) => version.id === selectedVersionId);
  const selectedScenarioKey = normalizeScenarioKey(
    selectedVersion?.scenarioKey ?? selectedSummary?.scenarioKey,
  );

  const scenarioMatch = versions
    .filter(
      (version) =>
        version.id !== selectedVersionId &&
        normalizeScenarioKey(version.scenarioKey) === selectedScenarioKey,
    )
    .sort(sortVersionsDescending)
    .find((version) => {
      if (!selectedSummary) {
        return true;
      }

      return version.versionNumber < selectedSummary.versionNumber;
    });

  if (scenarioMatch) {
    return scenarioMatch.id;
  }

  return (
    versions
      .filter((version) => version.id !== selectedVersionId)
      .sort(sortVersionsDescending)[0]?.id ?? ""
  );
}

export function buildForecastMonthlyComparisonRows(
  currentRollups: ForecastProjectMonthlyRollupRead[],
  comparisonRollups: ForecastProjectMonthlyRollupRead[],
): ForecastMonthlyComparisonRow[] {
  const currentMap = new Map(currentRollups.map((rollup) => [rollup.month, rollup]));
  const comparisonMap = new Map(
    comparisonRollups.map((rollup) => [rollup.month, rollup]),
  );

  return Array.from(
    new Set([...currentMap.keys(), ...comparisonMap.keys()]),
  )
    .sort((left, right) => toMonthValue(left) - toMonthValue(right))
    .map((month) => {
      const current = currentMap.get(month);
      const comparison = comparisonMap.get(month);
      const currentAmount = current?.amount ?? 0;
      const comparisonAmount = comparison?.amount ?? null;

      return {
        month,
        amount: currentAmount,
        weightedAmount: current?.weightedAmount ?? 0,
        lowAmount: current?.lowAmount ?? null,
        highAmount: current?.highAmount ?? null,
        actualAmount: current?.actualAmount ?? null,
        comparisonAmount,
        comparisonWeightedAmount: comparison?.weightedAmount ?? null,
        deltaAmount: Number((currentAmount - (comparison?.amount ?? 0)).toFixed(2)),
      };
    });
}

export function summarizeForecastProjectRollups(
  rollups: ForecastProjectMonthlyRollupRead[],
): ForecastRollupSummary {
  let peakMonth: string | null = null;
  let peakAmount = 0;
  let actualMonthCount = 0;
  let hasLowValues = false;
  let hasHighValues = false;
  let lowTotal = 0;
  let highTotal = 0;

  rollups.forEach((rollup) => {
    if (rollup.amount >= peakAmount) {
      peakMonth = rollup.month;
      peakAmount = rollup.amount;
    }

    if (rollup.actualAmount != null) {
      actualMonthCount += 1;
    }

    if (rollup.lowAmount != null) {
      hasLowValues = true;
      lowTotal += rollup.lowAmount;
    }

    if (rollup.highAmount != null) {
      hasHighValues = true;
      highTotal += rollup.highAmount;
    }
  });

  return {
    lowTotal: hasLowValues ? Number(lowTotal.toFixed(2)) : null,
    highTotal: hasHighValues ? Number(highTotal.toFixed(2)) : null,
    actualMonthCount,
    monthCount: rollups.length,
    peakMonth,
    peakAmount,
  };
}

export function summarizeForecastSanityChecks(
  detail: ForecastDetailRead | null | undefined,
  version: ForecastVersionRead | null | undefined,
): ForecastSanitySummary {
  const combinedChecks = dedupeSanityChecks([
    ...(detail?.sanityChecks ?? []),
    ...(version?.sanityChecks ?? []),
    ...((version?.lines ?? []).flatMap((line) => line.sanityChecks ?? [])),
  ]);
  const blockingChecks = combinedChecks.filter(
    (check) => check.blocking || check.severity === "error",
  );
  const warningChecks = combinedChecks.filter(
    (check) => !check.blocking && check.severity === "warning",
  );
  const blockingMessages = new Set(
    blockingChecks.map((check) => buildBlockingIssueMessage(check)),
  );
  const otherBlockingIssues = uniqueValues(
    (version?.issues ?? []).filter((issue) => !blockingMessages.has(issue)),
  );
  const checksByLineId = combinedChecks.reduce<
    Record<string, ForecastSanityCheckRead[]>
  >((result, check) => {
    if (!check.lineId) {
      return result;
    }
    const existing = result[check.lineId] ?? [];
    existing.push(check);
    result[check.lineId] = existing.sort(compareSanityChecks);
    return result;
  }, {});
  const checksByMonth = combinedChecks.reduce<
    Record<string, ForecastSanityCheckRead[]>
  >((result, check) => {
    if (!check.month) {
      return result;
    }
    const existing = result[check.month] ?? [];
    existing.push(check);
    result[check.month] = existing.sort(compareSanityChecks);
    return result;
  }, {});
  const blockingLineIds = uniqueValues(
    blockingChecks.map((check) => check.lineId ?? ""),
  );
  const warningLineIds = uniqueValues(
    warningChecks.map((check) => check.lineId ?? ""),
  );
  const blockingMonths = uniqueValues(
    blockingChecks.map((check) => check.month ?? ""),
  );
  const warningMonths = uniqueValues(
    warningChecks.map((check) => check.month ?? ""),
  );

  return {
    allChecks: combinedChecks,
    blockingChecks,
    warningChecks,
    otherBlockingIssues,
    allBlockingMessages: [
      ...blockingChecks.map((check) => buildBlockingIssueMessage(check)),
      ...otherBlockingIssues,
    ],
    confidenceChecks: combinedChecks.filter((check) =>
      CONFIDENCE_WARNING_KEYS.has(check.key),
    ),
    scenarioChecks: combinedChecks.filter((check) =>
      SCENARIO_WARNING_KEYS.has(check.key),
    ),
    checksByLineId,
    checksByMonth,
    blockingLineIds,
    warningLineIds,
    blockingMonths,
    warningMonths,
    affectedLineCount: uniqueValues([
      ...blockingLineIds,
      ...warningLineIds,
    ]).length,
    affectedMonthCount: uniqueValues([
      ...blockingMonths,
      ...warningMonths,
    ]).length,
  };
}
