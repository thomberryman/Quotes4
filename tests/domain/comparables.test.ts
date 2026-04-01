import { describe, expect, it } from "vitest";

import {
  buildComparableRecommendations,
  rankComparableProjects,
  scoreComparableProject
} from "../../packages/domain/src";
import type { ComparableProjectSnapshot } from "../../packages/domain/src";

function buildSnapshot(
  id: string,
  overrides: Partial<ComparableProjectSnapshot> = {}
): ComparableProjectSnapshot {
  return {
    id,
    projectName: `Project ${id}`,
    status: "complete",
    clientId: "client-1",
    clientName: "North Star Pictures",
    projectFormatKey: "trailer_promo",
    disciplineIds: ["offline", "online", "grade"],
    targetAmount: 100000,
    durationWeeks: 8,
    episodeCount: 1,
    quoteCurrencyCode: "GBP",
    primaryLanguageCode: "en-GB",
    deliverableKeys: ["final_picture_master", "caption_package"],
    localizationKeys: ["caption_package:en-GB"],
    complexityProfile: {
      finishing: "complex",
      audio: "standard",
      vfx: "low"
    },
    counterpartyCompanyIdsByRole: {
      client: ["client-1"],
      streamer: ["streamer-1"]
    },
    benchmarkSummary: {
      sourceQuoteVersionId: `quote-${id}`,
      currencyCode: "GBP",
      quotedAmount: 100000,
      actualAmount: 108000,
      quoteToActualVarianceAmount: 8000,
      quoteToActualVariancePct: 8,
      actualsStatus: "complete",
      actualsAsOfDate: "2026-03-31",
      disciplineSummaries: [
        {
          disciplineId: "offline",
          disciplineName: "Offline",
          quotedAmount: 40000,
          actualAmount: 43000,
          quoteToActualVarianceAmount: 3000,
          quoteToActualVariancePct: 7.5,
          actualsStatus: "complete"
        },
        {
          disciplineId: "online",
          disciplineName: "Online",
          quotedAmount: 35000,
          actualAmount: 38000,
          quoteToActualVarianceAmount: 3000,
          quoteToActualVariancePct: 8.57,
          actualsStatus: "complete"
        },
        {
          disciplineId: "grade",
          disciplineName: "Grade",
          quotedAmount: 25000,
          actualAmount: 27000,
          quoteToActualVarianceAmount: 2000,
          quoteToActualVariancePct: 8,
          actualsStatus: "complete"
        }
      ]
    },
    ...overrides
  };
}

describe("scoreComparableProject", () => {
  it("produces a weighted score, coverage, and detailed factor breakdown", () => {
    const score = scoreComparableProject(
      buildSnapshot("target"),
      buildSnapshot("candidate", {
        targetAmount: 108000,
        durationWeeks: 9,
        deliverableKeys: ["final_picture_master"],
        benchmarkSummary: {
          sourceQuoteVersionId: "quote-candidate",
          currencyCode: "GBP",
          quotedAmount: 108000,
          actualAmount: 114000,
          quoteToActualVarianceAmount: 6000,
          quoteToActualVariancePct: 5.56,
          actualsStatus: "complete",
          actualsAsOfDate: "2026-03-31",
          disciplineSummaries: []
        }
      })
    );

    expect(score.similarityScore).toBeGreaterThan(80);
    expect(score.coveragePct).toBe(100);
    expect(score.strength).toBe("strong");
    expect(
      score.matchedFactors.find((factor) => factor.factorKey === "client")?.awardedPoints
    ).toBe(15);
    expect(
      score.matchedFactors.find((factor) => factor.factorKey === "budget_band")?.detail
    ).toContain("within 10%");
  });
});

describe("rankComparableProjects", () => {
  it("suppresses weak auto suggestions but keeps manual overrides visible", () => {
    const target = buildSnapshot("target");
    const strongAuto = buildSnapshot("strong-auto", {
      targetAmount: 103000
    });
    const weakAuto = buildSnapshot("weak-auto", {
      clientId: "other-client",
      projectFormatKey: "feature_film",
      disciplineIds: ["vfx"],
      targetAmount: 240000,
      durationWeeks: 20,
      deliverableKeys: ["archive_turnover"],
      localizationKeys: ["dub:fr-FR"],
      primaryLanguageCode: "fr-FR"
    });
    const weakPinned = buildSnapshot("weak-pinned", {
      clientId: "other-client",
      projectFormatKey: "feature_film",
      disciplineIds: ["audio"],
      targetAmount: 220000,
      durationWeeks: 18,
      deliverableKeys: ["archive_turnover"]
    });
    const strongExcluded = buildSnapshot("strong-excluded", {
      targetAmount: 101000
    });

    const result = rankComparableProjects({
      target,
      candidates: [strongAuto, weakAuto, weakPinned, strongExcluded],
      pinnedProjectIds: ["weak-pinned"],
      excludedProjectIds: ["strong-excluded"],
      limit: 10
    });

    expect(result.items.map((item) => item.project.id)).toEqual([
      "weak-pinned",
      "strong-auto",
      "strong-excluded"
    ]);
    expect(result.items.find((item) => item.project.id === "weak-pinned")?.selectionState).toBe(
      "pinned"
    );
    expect(result.items.find((item) => item.project.id === "strong-excluded")?.selectionState).toBe(
      "excluded"
    );
    expect(result.items.some((item) => item.project.id === "weak-auto")).toBe(false);
  });
});

describe("buildComparableRecommendations", () => {
  it("returns null numeric ranges when too few eligible comparables remain", () => {
    const target = buildSnapshot("target");
    const result = buildComparableRecommendations({
      target,
      candidates: [
        buildSnapshot("candidate-1"),
        buildSnapshot("candidate-2", {
          status: "awarded",
          benchmarkSummary: {
            sourceQuoteVersionId: "quote-candidate-2",
            currencyCode: "GBP",
            quotedAmount: 112000,
            actualsStatus: "partial",
            disciplineSummaries: []
          }
        })
      ]
    });

    expect(result.overallQuoteRange).toBeNull();
    expect(result.overallActualInformedRange).toBeNull();
    expect(result.riskSignals.map((signal) => signal.key)).toContain("insufficient_comparables");
  });

  it("builds quote and actual-informed ranges with low-sample fallback and discipline detail", () => {
    const target = buildSnapshot("target");
    const result = buildComparableRecommendations({
      target,
      candidates: [
        buildSnapshot("candidate-1", {
          targetAmount: 98000,
          benchmarkSummary: {
            sourceQuoteVersionId: "quote-candidate-1",
            currencyCode: "GBP",
            quotedAmount: 98000,
            actualAmount: 105000,
            quoteToActualVarianceAmount: 7000,
            quoteToActualVariancePct: 7.14,
            actualsStatus: "complete",
            actualsAsOfDate: "2026-03-31",
            disciplineSummaries: [
              {
                disciplineId: "offline",
                disciplineName: "Offline",
                quotedAmount: 39000,
                actualAmount: 42000,
                quoteToActualVarianceAmount: 3000,
                quoteToActualVariancePct: 7.69,
                actualsStatus: "complete"
              }
            ]
          }
        }),
        buildSnapshot("candidate-2", {
          targetAmount: 110000,
          benchmarkSummary: {
            sourceQuoteVersionId: "quote-candidate-2",
            currencyCode: "GBP",
            quotedAmount: 110000,
            actualAmount: 119000,
            quoteToActualVarianceAmount: 9000,
            quoteToActualVariancePct: 8.18,
            actualsStatus: "complete",
            actualsAsOfDate: "2026-03-31",
            disciplineSummaries: [
              {
                disciplineId: "offline",
                disciplineName: "Offline",
                quotedAmount: 41000,
                actualAmount: 44500,
                quoteToActualVarianceAmount: 3500,
                quoteToActualVariancePct: 8.54,
                actualsStatus: "complete"
              }
            ]
          }
        }),
        buildSnapshot("candidate-3", {
          targetAmount: 122000,
          benchmarkSummary: {
            sourceQuoteVersionId: "quote-candidate-3",
            currencyCode: "GBP",
            quotedAmount: 122000,
            actualAmount: 131000,
            quoteToActualVarianceAmount: 9000,
            quoteToActualVariancePct: 7.38,
            actualsStatus: "complete",
            actualsAsOfDate: "2026-03-31",
            disciplineSummaries: [
              {
                disciplineId: "offline",
                disciplineName: "Offline",
                quotedAmount: 45000,
                actualAmount: 48500,
                quoteToActualVarianceAmount: 3500,
                quoteToActualVariancePct: 7.78,
                actualsStatus: "complete"
              }
            ]
          }
        })
      ]
    });

    expect(result.overallQuoteRange).not.toBeNull();
    expect(result.overallQuoteRange?.methodology).toBe("min_median_max");
    expect(result.overallQuoteRange).toMatchObject({
      low: 98000,
      high: 122000,
      sampleSize: 3
    });
    expect(result.overallActualInformedRange?.median).toBeGreaterThan(
      result.overallQuoteRange!.median
    );
    expect(result.disciplineRanges[0]).toMatchObject({
      disciplineId: "offline",
      sampleSize: 3
    });
    expect(result.comparablesUsed).toEqual(["candidate-1", "candidate-2", "candidate-3"]);
  });
});
