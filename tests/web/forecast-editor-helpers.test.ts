import { describe, expect, it } from "vitest";

import type {
  ForecastDetailRead,
  ForecastLineRead,
  ForecastMonthlyAllocationRead,
  ForecastProjectMonthlyRollupRead,
  ForecastSanityCheckRead,
  ForecastVersionRead,
  ForecastVersionSummaryRead,
} from "../../packages/contracts/src/generated/api-types";

import {
  buildForecastMonthlyComparisonRows,
  buildForecastScenarioOptions,
  getDefaultForecastComparisonVersionId,
  summarizeForecastSanityChecks,
  summarizeForecastProjectRollups,
} from "../../apps/web/components/features/forecasts/forecast-editor-helpers";

function buildVersionSummary(
  overrides: Partial<ForecastVersionSummaryRead>,
): ForecastVersionSummaryRead {
  return {
    id: overrides.id ?? "version_1",
    forecastId: overrides.forecastId ?? "forecast_1",
    versionNumber: overrides.versionNumber ?? 1,
    status: overrides.status ?? "draft",
    title: overrides.title ?? null,
    outcomeTypeSnapshot: overrides.outcomeTypeSnapshot ?? "bid",
    probabilityPercent: overrides.probabilityPercent ?? 100,
    totalAmount: overrides.totalAmount ?? 10000,
    weightedTotalAmount: overrides.weightedTotalAmount ?? 10000,
    scenarioKey: overrides.scenarioKey ?? "base",
    engineSource: overrides.engineSource ?? "unified_forecast_engine",
    predictionRunId: overrides.predictionRunId ?? null,
    predictionScenarioKey: overrides.predictionScenarioKey ?? null,
    confidenceScore: overrides.confidenceScore ?? null,
    dataSufficiencyScore: overrides.dataSufficiencyScore ?? null,
    fallbackTier: overrides.fallbackTier ?? null,
    changeSummary: overrides.changeSummary ?? null,
    sourceQuoteVersionId: overrides.sourceQuoteVersionId ?? null,
    isSourceQuoteCurrent: overrides.isSourceQuoteCurrent ?? true,
    createdAt: overrides.createdAt ?? "2026-04-01T09:00:00Z",
    updatedAt: overrides.updatedAt ?? "2026-04-01T09:00:00Z",
  };
}

function buildVersionRead(
  overrides: Partial<ForecastVersionRead>,
): ForecastVersionRead {
  return {
    ...buildVersionSummary(overrides),
    notesText: overrides.notesText ?? null,
    revisionReason: overrides.revisionReason ?? null,
    parentVersionId: overrides.parentVersionId ?? null,
    explanationSummary: overrides.explanationSummary ?? null,
    sanityChecks: overrides.sanityChecks ?? [],
    issues: overrides.issues ?? [],
    lines: overrides.lines ?? [],
    disciplineMonthlyRollups: overrides.disciplineMonthlyRollups ?? [],
    projectMonthlyRollups: overrides.projectMonthlyRollups ?? [],
  };
}

function buildDetailRead(
  overrides: Partial<ForecastDetailRead>,
): ForecastDetailRead {
  return {
    forecastId: overrides.forecastId ?? "forecast_1",
    projectId: overrides.projectId ?? "project_1",
    currentVersionId: overrides.currentVersionId ?? "version_1",
    versions: overrides.versions ?? [],
    currentVersion: overrides.currentVersion ?? null,
    sanityChecks: overrides.sanityChecks ?? [],
  };
}

function buildRollup(
  overrides: Partial<ForecastProjectMonthlyRollupRead>,
): ForecastProjectMonthlyRollupRead {
  return {
    month: overrides.month ?? "2026-01",
    amount: overrides.amount ?? 0,
    weightedAmount: overrides.weightedAmount ?? 0,
    lowAmount: overrides.lowAmount ?? null,
    highAmount: overrides.highAmount ?? null,
    actualAmount: overrides.actualAmount ?? null,
  };
}

function buildAllocation(
  overrides: Partial<ForecastMonthlyAllocationRead>,
): ForecastMonthlyAllocationRead {
  return {
    month: overrides.month ?? "2026-01",
    amount: overrides.amount ?? 0,
    weightedAmount: overrides.weightedAmount ?? 0,
    lowAmount: overrides.lowAmount ?? null,
    highAmount: overrides.highAmount ?? null,
    actualAmount: overrides.actualAmount ?? null,
    allocationSource: overrides.allocationSource ?? "forecast",
    sourceContext: overrides.sourceContext ?? null,
  };
}

function buildLineRead(overrides: Partial<ForecastLineRead>): ForecastLineRead {
  return {
    id: overrides.id ?? "line_1",
    sourceLineId: overrides.sourceLineId ?? "quote_line_1",
    label: overrides.label ?? "Offline edit",
    totalAmount: overrides.totalAmount ?? 10000,
    weightedTotalAmount: overrides.weightedTotalAmount ?? 10000,
    currencyCode: overrides.currencyCode ?? "GBP",
    allocationMethod: overrides.allocationMethod ?? "schedule",
    disciplineId: overrides.disciplineId ?? "discipline_offline",
    scheduleRangeId: overrides.scheduleRangeId ?? null,
    notes: overrides.notes ?? null,
    forecastMethodKey: overrides.forecastMethodKey ?? "curve_profile",
    allocationProfileKey: overrides.allocationProfileKey ?? "front_loaded",
    sequencingTemplateKey: overrides.sequencingTemplateKey ?? null,
    sequencingStageKey: overrides.sequencingStageKey ?? null,
    overlapPercent: overrides.overlapPercent ?? null,
    confidenceScore: overrides.confidenceScore ?? null,
    dataSufficiencyScore: overrides.dataSufficiencyScore ?? null,
    fallbackTier: overrides.fallbackTier ?? null,
    actualsToDateAmount: overrides.actualsToDateAmount ?? null,
    remainingAmount: overrides.remainingAmount ?? null,
    forecastInputs: overrides.forecastInputs ?? null,
    explanations: overrides.explanations ?? [],
    sanityChecks: overrides.sanityChecks ?? [],
    issues: overrides.issues ?? [],
    allocations: overrides.allocations ?? [buildAllocation({ amount: 10000 })],
  };
}

function buildSanityCheck(
  overrides: Partial<ForecastSanityCheckRead>,
): ForecastSanityCheckRead {
  return {
    key: overrides.key ?? "fallback_tier_missing",
    severity: overrides.severity ?? "warning",
    scope: overrides.scope ?? "version",
    title: overrides.title ?? "Fallback tier is not recorded",
    detail:
      overrides.detail ??
      "The forecast engine output does not say whether it used a strong or weak fallback tier.",
    recommendation: overrides.recommendation ?? "Persist the fallback tier.",
    blocking: overrides.blocking ?? false,
    lineId: overrides.lineId ?? null,
    month: overrides.month ?? null,
  };
}

describe("forecast editor helpers", () => {
  it("groups scenario options and keeps the latest version in each scenario", () => {
    const options = buildForecastScenarioOptions([
      buildVersionSummary({
        id: "base_v1",
        versionNumber: 1,
        scenarioKey: "base",
        weightedTotalAmount: 10000,
        confidenceScore: 70,
      }),
      buildVersionSummary({
        id: "upside_v2",
        versionNumber: 2,
        scenarioKey: "upside",
        weightedTotalAmount: 18000,
        confidenceScore: 60,
      }),
      buildVersionSummary({
        id: "base_v3",
        versionNumber: 3,
        scenarioKey: "base",
        weightedTotalAmount: 14000,
        confidenceScore: 82,
      }),
      buildVersionSummary({
        id: "custom_v1",
        versionNumber: 4,
        scenarioKey: "regional_stretch",
        weightedTotalAmount: 22000,
      }),
    ]);

    expect(options.map((option) => option.scenarioKey)).toEqual([
      "base",
      "upside",
      "regional_stretch",
    ]);
    expect(options[0]).toMatchObject({
      latestVersionId: "base_v3",
      latestVersionNumber: 3,
      count: 2,
      weightedTotalAmount: 14000,
      confidenceScore: 82,
    });
  });

  it("defaults comparison to the parent version, then same-scenario history, then any prior version", () => {
    const versions = [
      buildVersionSummary({
        id: "base_v1",
        versionNumber: 1,
        scenarioKey: "base",
      }),
      buildVersionSummary({
        id: "base_v2",
        versionNumber: 2,
        scenarioKey: "base",
      }),
      buildVersionSummary({
        id: "upside_v3",
        versionNumber: 3,
        scenarioKey: "upside",
      }),
    ];

    expect(
      getDefaultForecastComparisonVersionId(
        "upside_v3",
        buildVersionRead({
          id: "upside_v3",
          versionNumber: 3,
          scenarioKey: "upside",
          parentVersionId: "base_v2",
        }),
        versions,
      ),
    ).toBe("base_v2");

    expect(
      getDefaultForecastComparisonVersionId(
        "base_v2",
        buildVersionRead({
          id: "base_v2",
          versionNumber: 2,
          scenarioKey: "base",
          parentVersionId: null,
        }),
        versions,
      ),
    ).toBe("base_v1");

    expect(
      getDefaultForecastComparisonVersionId(
        "base_v1",
        buildVersionRead({
          id: "base_v1",
          versionNumber: 1,
          scenarioKey: "base",
          parentVersionId: null,
        }),
        versions,
      ),
    ).toBe("upside_v3");
  });

  it("builds month comparison rows across both versions", () => {
    const rows = buildForecastMonthlyComparisonRows(
      [
        buildRollup({
          month: "2026-01",
          amount: 12000,
          weightedAmount: 6000,
          lowAmount: 10000,
          highAmount: 14000,
        }),
        buildRollup({
          month: "2026-03",
          amount: 4000,
          weightedAmount: 2000,
          actualAmount: 3900,
        }),
      ],
      [
        buildRollup({
          month: "2026-02",
          amount: 8000,
          weightedAmount: 4000,
        }),
        buildRollup({
          month: "2026-03",
          amount: 3000,
          weightedAmount: 1500,
        }),
      ],
    );

    expect(rows).toEqual([
      {
        month: "2026-01",
        amount: 12000,
        weightedAmount: 6000,
        lowAmount: 10000,
        highAmount: 14000,
        actualAmount: null,
        comparisonAmount: null,
        comparisonWeightedAmount: null,
        deltaAmount: 12000,
      },
      {
        month: "2026-02",
        amount: 0,
        weightedAmount: 0,
        lowAmount: null,
        highAmount: null,
        actualAmount: null,
        comparisonAmount: 8000,
        comparisonWeightedAmount: 4000,
        deltaAmount: -8000,
      },
      {
        month: "2026-03",
        amount: 4000,
        weightedAmount: 2000,
        lowAmount: null,
        highAmount: null,
        actualAmount: 3900,
        comparisonAmount: 3000,
        comparisonWeightedAmount: 1500,
        deltaAmount: 1000,
      },
    ]);
  });

  it("summarizes project rollups for the monthly header", () => {
    expect(
      summarizeForecastProjectRollups([
        buildRollup({
          month: "2026-01",
          amount: 5000,
          weightedAmount: 2500,
          lowAmount: 4500,
          highAmount: 6000,
        }),
        buildRollup({
          month: "2026-02",
          amount: 9000,
          weightedAmount: 4500,
          lowAmount: 8500,
          highAmount: 9800,
          actualAmount: 9100,
        }),
      ]),
    ).toEqual({
      lowTotal: 13000,
      highTotal: 15800,
      actualMonthCount: 1,
      monthCount: 2,
      peakMonth: "2026-02",
      peakAmount: 9000,
    });
  });

  it("summarizes sanity checks by severity, month, line, scenario, and confidence context", () => {
    const lineBlockingCheck = buildSanityCheck({
      key: "actuals_not_replacing_forecast",
      severity: "error",
      scope: "line",
      title: "Completed actuals are not replacing forecast values",
      detail:
        "Offline edit has 4500.00 posted for 2026-02, but the forecast row is not fully anchored to actuals.",
      recommendation: "Replace completed-month forecast values with posted actuals.",
      blocking: true,
      lineId: "line_offline",
      month: "2026-02",
    });
    const lineConfidenceCheck = buildSanityCheck({
      key: "narrow_bands_sparse_data",
      scope: "line",
      title: "Forecast bands are narrow despite sparse data",
      detail:
        "Offline edit has data sufficiency 32.0 but its forecast band remains tighter than expected.",
      lineId: "line_offline",
      month: "2026-03",
    });
    const scenarioCheck = buildSanityCheck({
      key: "scenario_outputs_too_similar",
      scope: "detail",
      title: "Scenario outputs are too similar to be decision-useful",
      detail:
        "Scenario versions (base, downside, upside) differ by less than 3% of the base total.",
    });
    const versionConfidenceCheck = buildSanityCheck({
      key: "confidence_too_high_for_metadata",
      scope: "version",
      title: "Confidence looks too high for the available metadata",
      detail:
        "The forecast confidence score is 88.0 while metadata completeness is only 42.0.",
    });
    const summary = summarizeForecastSanityChecks(
      buildDetailRead({
        sanityChecks: [scenarioCheck],
      }),
      buildVersionRead({
        sanityChecks: [scenarioCheck, versionConfidenceCheck],
        issues: [
          `${lineBlockingCheck.title}: ${lineBlockingCheck.detail}`,
          "Forecast source quote version is no longer current. Recalculate or create a new draft from the current quote.",
        ],
        lines: [
          buildLineRead({
            id: "line_offline",
            label: "Offline edit",
            sanityChecks: [lineBlockingCheck, lineConfidenceCheck],
          }),
        ],
      }),
    );

    expect(summary.blockingChecks).toEqual([lineBlockingCheck]);
    expect(summary.warningChecks).toEqual([
      scenarioCheck,
      versionConfidenceCheck,
      lineConfidenceCheck,
    ]);
    expect(summary.scenarioChecks).toEqual([scenarioCheck]);
    expect(summary.confidenceChecks).toEqual([
      versionConfidenceCheck,
      lineConfidenceCheck,
    ]);
    expect(summary.checksByLineId.line_offline).toEqual([
      lineBlockingCheck,
      lineConfidenceCheck,
    ]);
    expect(summary.checksByMonth["2026-02"]).toEqual([lineBlockingCheck]);
    expect(summary.checksByMonth["2026-03"]).toEqual([lineConfidenceCheck]);
    expect(summary.otherBlockingIssues).toEqual([
      "Forecast source quote version is no longer current. Recalculate or create a new draft from the current quote.",
    ]);
    expect(summary.allBlockingMessages).toEqual([
      `${lineBlockingCheck.title}: ${lineBlockingCheck.detail}`,
      "Forecast source quote version is no longer current. Recalculate or create a new draft from the current quote.",
    ]);
    expect(summary.blockingLineIds).toEqual(["line_offline"]);
    expect(summary.warningLineIds).toEqual(["line_offline"]);
    expect(summary.blockingMonths).toEqual(["2026-02"]);
    expect(summary.warningMonths).toEqual(["2026-03"]);
    expect(summary.affectedLineCount).toBe(1);
    expect(summary.affectedMonthCount).toBe(2);
  });
});
