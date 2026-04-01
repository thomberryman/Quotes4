import { describe, expect, it } from "vitest";

import {
  applyManualForecastOverride,
  buildScheduleMonthlyAllocations,
  calculateForecastVersion,
  resolveForecastOutcomeBucket,
  summarizeVariance,
  validateManualMonthlyAllocations
} from "../../packages/domain/src";

describe("buildScheduleMonthlyAllocations", () => {
  it("spreads value across calendar months and preserves the total", () => {
    const allocations = buildScheduleMonthlyAllocations({
      startDate: "2026-01-20",
      endDate: "2026-02-10",
      amount: 2200,
      currencyCode: "GBP"
    });

    expect(allocations).toEqual([
      { month: "2026-01", amount: 1200, amountInCents: 120000 },
      { month: "2026-02", amount: 1000, amountInCents: 100000 }
    ]);
  });

  it("balances rounding so the month spread still equals the source amount", () => {
    const allocations = buildScheduleMonthlyAllocations({
      startDate: "2026-01-31",
      endDate: "2026-02-02",
      amount: 100,
      currencyCode: "GBP"
    });

    expect(allocations).toEqual([
      { month: "2026-01", amount: 33.33, amountInCents: 3333 },
      { month: "2026-02", amount: 66.67, amountInCents: 6667 }
    ]);
  });
});

describe("validateManualMonthlyAllocations", () => {
  it("accepts balanced allocations", () => {
    const result = validateManualMonthlyAllocations({
      expectedAmount: 5000,
      allocations: [
        { month: "2026-03", amount: 2500 },
        { month: "2026-04", amount: 2500 }
      ]
    });

    expect(result.isValid).toBe(true);
    expect(result.differenceFromExpected).toBe(0);
  });

  it("rejects duplicate or unbalanced allocations", () => {
    const result = validateManualMonthlyAllocations({
      expectedAmount: 1000,
      allocations: [
        { month: "2026-03", amount: 600 },
        { month: "2026-03", amount: 300 }
      ]
    });

    expect(result.isValid).toBe(false);
    expect(result.issues).toContain("Duplicate manual allocation month: 2026-03");
  });
});

describe("resolveForecastOutcomeBucket", () => {
  it("treats active projects as awarded and lost status as terminal", () => {
    expect(
      resolveForecastOutcomeBucket({
        projectStatus: "active",
        outcomes: [{ outcomeType: "bid", effectiveAt: "2026-03-01" }]
      })
    ).toBe("awarded");

    expect(
      resolveForecastOutcomeBucket({
        projectStatus: "lost",
        outcomes: [{ outcomeType: "awarded", effectiveAt: "2026-03-10" }]
      })
    ).toBe("lost");
  });
});

describe("calculateForecastVersion", () => {
  it("splits schedule lines across multiple discipline ranges and applies weighting", () => {
    const result = calculateForecastVersion({
      projectStatus: "bid",
      probabilityPercent: 50,
      outcomes: [{ outcomeType: "bid", effectiveAt: "2026-03-01" }],
      scheduleRanges: [
        {
          id: "prep",
          label: "Prep",
          disciplineId: "picture",
          startDate: "2026-04-01",
          endDate: "2026-04-30",
          allocationPercent: 40
        },
        {
          id: "finish",
          label: "Finish",
          disciplineId: "picture",
          startDate: "2026-05-01",
          endDate: "2026-05-31",
          allocationPercent: 60
        }
      ],
      lines: [
        {
          id: "line_picture",
          label: "Picture",
          disciplineId: "picture",
          allocationMethod: "schedule",
          totalAmount: 10000,
          currencyCode: "GBP"
        }
      ]
    });

    expect(result.outcomeTypeSnapshot).toBe("bid");
    expect(result.totalAmount).toBe(10000);
    expect(result.weightedTotalAmount).toBe(5000);
    expect(result.lines).toHaveLength(2);
    expect(result.lines.map((line) => line.totalAmount)).toEqual([4000, 6000]);
    expect(result.projectMonthlyRollups).toEqual([
      {
        month: "2026-04",
        amount: 4000,
        amountInCents: 400000,
        weightedAmount: 2000,
        weightedAmountInCents: 200000
      },
      {
        month: "2026-05",
        amount: 6000,
        amountInCents: 600000,
        weightedAmount: 3000,
        weightedAmountInCents: 300000
      }
    ]);
  });

  it("surfaces invalid schedule ranges as issues and excludes them from totals", () => {
    const result = calculateForecastVersion({
      projectStatus: "bid",
      probabilityPercent: 75,
      outcomes: [{ outcomeType: "bid", effectiveAt: "2026-03-01" }],
      scheduleRanges: [],
      lines: [
        {
          id: "line_picture",
          label: "Picture",
          disciplineId: "picture",
          allocationMethod: "schedule",
          totalAmount: 10000,
          currencyCode: "GBP"
        }
      ]
    });

    expect(result.totalAmount).toBe(0);
    expect(result.issues).toContain('Picture: No schedule ranges were found for "Picture".');
  });

  it("forces awarded and lost probabilities", () => {
    const awarded = calculateForecastVersion({
      projectStatus: "awarded",
      probabilityPercent: 40,
      outcomes: [{ outcomeType: "awarded", effectiveAt: "2026-03-05" }],
      scheduleRanges: [],
      lines: [
        {
          id: "line_manual",
          label: "Manual",
          disciplineId: "sound",
          allocationMethod: "manual",
          totalAmount: 1000,
          currencyCode: "GBP",
          allocations: [{ month: "2026-04", amount: 1000 }]
        }
      ]
    });

    const lost = calculateForecastVersion({
      projectStatus: "lost",
      probabilityPercent: 80,
      outcomes: [{ outcomeType: "lost", effectiveAt: "2026-03-06" }],
      scheduleRanges: [],
      lines: [
        {
          id: "line_manual",
          label: "Manual",
          disciplineId: "sound",
          allocationMethod: "manual",
          totalAmount: 1000,
          currencyCode: "GBP",
          allocations: [{ month: "2026-04", amount: 1000 }]
        }
      ]
    });

    expect(awarded.probabilityPercent).toBe(100);
    expect(awarded.weightedTotalAmount).toBe(1000);
    expect(lost.probabilityPercent).toBe(0);
    expect(lost.weightedTotalAmount).toBe(0);
  });
});

describe("applyManualForecastOverride", () => {
  it("converts a schedule line into a manual line with a reason", () => {
    const override = applyManualForecastOverride({
      line: {
        id: "line_picture",
        label: "Picture",
        totalAmount: 5000,
        currencyCode: "GBP",
        disciplineId: "picture",
        notes: "Original schedule"
      },
      allocations: [
        { month: "2026-04", amount: 2000 },
        { month: "2026-05", amount: 3000 }
      ],
      reason: "Client requested front-loading"
    });

    expect(override.allocationMethod).toBe("manual");
    expect(override.notes).toContain("Manual override: Client requested front-loading");
  });
});

describe("summarizeVariance", () => {
  it("calculates quote and forecast variance against actuals", () => {
    expect(
      summarizeVariance({
        quotedAmount: 10000,
        forecastAmount: 11000,
        actualAmount: 10500
      })
    ).toEqual({
      quotedAmount: 10000,
      forecastAmount: 11000,
      actualAmount: 10500,
      quoteToActualVariance: 500,
      forecastToActualVariance: -500
    });
  });
});
