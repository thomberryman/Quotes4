// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  PredictionRunDetailRead,
  PredictionRunSummaryRead,
  ProjectRead,
} from "@quotes4/contracts";

import { ProjectScenarioWorkspace } from "../../apps/web/components/features/predictions/project-scenario-workspace";

const apiClient = {
  createPredictionRun: vi.fn(),
  getPredictionRun: vi.fn(),
  getProject: vi.fn(),
  listPredictionRuns: vi.fn(),
  patchPredictionOverrides: vi.fn(),
  promotePredictionScenario: vi.fn(),
  putProjectMetadata: vi.fn(),
  updatePredictionScenario: vi.fn(),
  updateProject: vi.fn(),
};

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api/browser-client", () => ({
  getBrowserApiClient: () => apiClient,
}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function buildProject(): ProjectRead {
  return {
    id: "project_alpha",
    code: "ALPHA",
    name: "Project Alpha",
    status: "bid",
    pipelineStageKey: "negotiation",
    strategicAccountFlag: true,
    quoteCurrencyCode: "GBP",
    updatedAt: "2026-04-02T12:00:00Z",
    metadata: {
      projectFormatKey: "trailer_promo",
      durationWeeks: 6,
      episodeCount: 1,
      genre: "Drama",
      language: "en-GB",
      budgetTarget: 124000,
      metadata: null,
    },
  } as ProjectRead;
}

function buildRunSummary(): PredictionRunSummaryRead {
  return {
    id: "run_alpha",
    projectId: "project_alpha",
    quoteVersionId: "quote_version_1",
    forecastVersionId: null,
    modelVersion: "predictive_layer_v2",
    strategyKey: "deterministic",
    maturityStage: "stage_2",
    primaryEvidenceSource: "actual_informed_history",
    fallbackTier: "high_similarity_history",
    featureReadinessScore: 82,
    dataSufficiencyScore: 79,
    confidenceScore: 76,
    confidenceLabel: "high",
    expectedScenarioKey: "base",
    methodologySummary:
      "Comparable guidance with separate revenue and spend signals.",
    generatedAt: "2026-04-02T12:00:00Z",
    createdAt: "2026-04-02T12:00:00Z",
    updatedAt: "2026-04-02T12:00:00Z",
  } as PredictionRunSummaryRead;
}

function buildRun(): PredictionRunDetailRead {
  return {
    ...buildRunSummary(),
    target: {
      projectId: "project_alpha",
      projectName: "Project Alpha",
      quoteCurrencyCode: "GBP",
      quoteVersionId: "quote_version_1",
      projectFormatKey: "trailer_promo",
    },
    modelInfo: {
      strategy: "deterministic",
      refreshedAt: "2026-04-02T12:00:00Z",
      updateApproach: "Recomputed from persisted comparable evidence.",
      comparableProjectsConsidered: 5,
      comparableProjectsUsed: 3,
      completeActualHistoryCount: 3,
      monthlyProfileCount: 2,
    },
    likelyQuoteRange: {
      basis: "actual_informed_history",
      confidence: "high",
      low: 118000,
      median: 124000,
      high: 130000,
      currencyCode: "GBP",
      sampleSize: 3,
      comparableProjectIds: [
        "project_comp_1",
        "project_comp_2",
        "project_comp_3",
      ],
      methodology: "Median of comparable and actual-informed guidance.",
      reasoning: [
        "Comparable quote and actual history is sufficiently strong.",
      ],
      recommendedLow: 120000,
      recommendedMedian: 124000,
      recommendedHigh: 129000,
      acceptanceStatus: "pending_review",
    },
    disciplineUsage: [],
    monthlyRevenueSpread: [],
    overrunRisk: {
      level: "medium",
      flags: [],
    },
    riskSignals: [],
    winProbability: {
      probabilityPct: 55,
      probabilityBand: "medium",
      confidence: "high",
      confidenceScore: 74,
      fallbackTier: "high_similarity_history",
      keyFactors: [],
      reasoning: [
        "Commercial inputs place the bid in the middle probability band.",
      ],
    },
    scenarios: [
      {
        scenarioKey: "base",
        title: "Base",
        isExpected: true,
        updatedAt: "2026-04-02T12:00:00Z",
        assumptionOverrides: {
          quoteMultiplier: 1,
          actualMultiplier: 1,
          varianceDeltaPct: 0,
          winProbabilityDeltaPct: 0,
          scheduleShiftMonths: 0,
        },
        likelyQuoteRange: {
          basis: "actual_informed_history",
          confidence: "high",
          low: 118000,
          median: 124000,
          high: 130000,
          currencyCode: "GBP",
          sampleSize: 3,
          comparableProjectIds: [
            "project_comp_1",
            "project_comp_2",
            "project_comp_3",
          ],
          methodology: "Median quote guidance.",
          reasoning: ["Comparable quote history remains stable."],
          recommendedLow: 120000,
          recommendedMedian: 124000,
          recommendedHigh: 129000,
        },
        spendSummary: {
          currentActualCost: 28000,
          predictedTotalCost: 72000,
          predictedRemainingCost: 44000,
          impliedMarginAmount: 52000,
          impliedMarginPct: 41.94,
          confidence: "high",
          confidenceScore: 78,
          fallbackTier: "high_similarity_history",
          basis: "comparable_cost_history",
          disciplineSpend: [
            {
              disciplineId: "discipline_offline",
              disciplineCode: "offline",
              disciplineName: "Offline",
              currentActualCost: 18000,
              predictedTotalCost: 42000,
              predictedRemainingCost: 24000,
              costSharePct: 58.33,
              confidence: "high",
              sampleSize: 3,
              reasoning: [
                "Cost-share history available in 3 comparable project(s).",
              ],
            },
            {
              disciplineId: "discipline_online",
              disciplineCode: "online",
              disciplineName: "Online",
              currentActualCost: 10000,
              predictedTotalCost: 30000,
              predictedRemainingCost: 20000,
              costSharePct: 41.67,
              confidence: "medium",
              sampleSize: 2,
              reasoning: ["Comparable history is thinner for this discipline."],
            },
          ],
        },
        disciplineUsage: [
          {
            disciplineId: "discipline_offline",
            disciplineCode: "offline",
            disciplineName: "Offline",
            sampleSize: 3,
            usageRatePct: 95,
            predictedSharePct: 42,
            predictedAmountLow: 43000,
            predictedAmountMedian: 50000,
            predictedAmountHigh: 56000,
            predictedActualAmount: 50000,
            predictedVariancePct: 6,
            observedVarianceMedianPct: 5,
            confidence: "high",
            confidenceScore: 78,
            dataSufficiencyScore: 76,
            fallbackTier: "high_similarity_history",
            overrunRisk: "medium",
            isTargetDiscipline: true,
            comparableProjectIds: [
              "project_comp_1",
              "project_comp_2",
              "project_comp_3",
            ],
            keyDrivers: ["Historical overrun pattern."],
            reasoning: [
              "Revenue-outturn guidance remains a separate advisory input.",
            ],
          },
        ],
        monthlyRevenueSpread: [],
        overrunRisk: {
          level: "medium",
          flags: [],
        },
        winProbability: {
          probabilityPct: 55,
          probabilityBand: "medium",
          confidence: "high",
          confidenceScore: 74,
          fallbackTier: "high_similarity_history",
          keyFactors: [],
          reasoning: ["Base scenario keeps the default probability."],
        },
        projectedTotalRevenue: 124000,
        projectedWeightedRevenue: 68200,
      },
      {
        scenarioKey: "downside",
        title: "Downside",
        isExpected: false,
        updatedAt: "2026-04-02T12:05:00Z",
        assumptionOverrides: {
          quoteMultiplier: 1,
          actualMultiplier: 1.15,
          varianceDeltaPct: 6,
          winProbabilityDeltaPct: -10,
          scheduleShiftMonths: 1,
        },
        likelyQuoteRange: {
          basis: "actual_informed_history",
          confidence: "high",
          low: 118000,
          median: 118000,
          high: 126000,
          currencyCode: "GBP",
          sampleSize: 3,
          comparableProjectIds: [
            "project_comp_1",
            "project_comp_2",
            "project_comp_3",
          ],
          methodology: "Downside quote guidance.",
          reasoning: ["Revenue guidance remains distinct from spend guidance."],
          recommendedLow: 116000,
          recommendedMedian: 118000,
          recommendedHigh: 124000,
        },
        spendSummary: {
          currentActualCost: 28000,
          predictedTotalCost: 82800,
          predictedRemainingCost: 54800,
          impliedMarginAmount: 35200,
          impliedMarginPct: 29.83,
          confidence: "medium",
          confidenceScore: 73,
          fallbackTier: "high_similarity_history",
          basis: "comparable_cost_history",
          disciplineSpend: [
            {
              disciplineId: "discipline_offline",
              disciplineCode: "offline",
              disciplineName: "Offline",
              currentActualCost: 18000,
              predictedTotalCost: 48300,
              predictedRemainingCost: 30300,
              costSharePct: 58.33,
              confidence: "high",
              sampleSize: 3,
              reasoning: ["Comparable cost-share history remains primary."],
            },
            {
              disciplineId: "discipline_online",
              disciplineCode: "online",
              disciplineName: "Online",
              currentActualCost: 10000,
              predictedTotalCost: 34500,
              predictedRemainingCost: 24500,
              costSharePct: 41.67,
              confidence: "medium",
              sampleSize: 2,
              reasoning: ["Comparable history remains secondary."],
            },
          ],
        },
        disciplineUsage: [
          {
            disciplineId: "discipline_offline",
            disciplineCode: "offline",
            disciplineName: "Offline",
            sampleSize: 3,
            usageRatePct: 95,
            predictedSharePct: 42,
            predictedAmountLow: 46000,
            predictedAmountMedian: 56000,
            predictedAmountHigh: 62000,
            predictedActualAmount: 56000,
            predictedVariancePct: 12,
            observedVarianceMedianPct: 5,
            confidence: "high",
            confidenceScore: 74,
            dataSufficiencyScore: 76,
            fallbackTier: "high_similarity_history",
            overrunRisk: "high",
            isTargetDiscipline: true,
            comparableProjectIds: [
              "project_comp_1",
              "project_comp_2",
              "project_comp_3",
            ],
            keyDrivers: ["Scenario downside pressure."],
            reasoning: ["Revenue-outturn guidance stays separate from spend."],
          },
        ],
        monthlyRevenueSpread: [],
        overrunRisk: {
          level: "high",
          flags: [],
        },
        winProbability: {
          probabilityPct: 45,
          probabilityBand: "medium",
          confidence: "high",
          confidenceScore: 74,
          fallbackTier: "high_similarity_history",
          keyFactors: [],
          reasoning: ["Downside assumptions reduce commercial confidence."],
        },
        projectedTotalRevenue: 118000,
        projectedWeightedRevenue: 53100,
      },
    ],
    topComparables: [],
    moduleOutputs: [],
    overrides: [],
    evaluations: [],
    missingCriticalInputs: [],
    featureSnapshot: {},
    requestContext: {
      limit: 25,
      projectId: "project_alpha",
    },
    sourceReferences: [],
  } as PredictionRunDetailRead;
}

async function flushEffects() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  });
}

function findButtonByText(
  container: HTMLElement,
  label: string,
): HTMLButtonElement {
  const button = Array.from(container.querySelectorAll("button")).find(
    (candidate) => candidate.textContent?.trim() === label,
  );
  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Button not found: ${label}`);
  }
  return button;
}

type RenderedWorkspace = {
  container: HTMLDivElement;
  queryClient: QueryClient;
  root: Root;
};

async function renderWorkspace(): Promise<RenderedWorkspace> {
  const initialProject = buildProject();
  const initialRun = buildRun();
  const initialRunList = [buildRunSummary()];
  const container = document.createElement("div");
  document.body.appendChild(container);
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  const root = createRoot(container);

  await act(async () => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <ProjectScenarioWorkspace
          initialProject={initialProject}
          initialRun={initialRun}
          initialRunList={initialRunList}
          projectId="project_alpha"
        />
      </QueryClientProvider>,
    );
  });

  await flushEffects();

  return { container, queryClient, root };
}

describe("ProjectScenarioWorkspace", () => {
  beforeEach(() => {
    const run = buildRun();
    apiClient.listPredictionRuns.mockResolvedValue({
      items: [buildRunSummary()],
    });
    apiClient.getPredictionRun.mockResolvedValue(run);
    apiClient.getProject.mockResolvedValue(buildProject());
  });

  afterEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("renders advisory spend outlook separately from revenue outturn guidance and updates with scenario switches", async () => {
    const { container, queryClient, root } = await renderWorkspace();

    expect(container.textContent).toContain("Advisory Spend Outlook");
    expect(container.textContent).toContain("Revenue Outturn Outlook");
    expect(container.textContent).toContain("Predicted total spend");
    expect(container.textContent).toContain("£72,000.00");
    expect(container.textContent).toContain("£44,000.00");
    expect(container.textContent).toContain("£52,000.00");

    await act(async () => {
      findButtonByText(container, "Downside").click();
    });
    await flushEffects();

    expect(container.textContent).toContain("£82,800.00");
    expect(container.textContent).toContain("£54,800.00");
    expect(container.textContent).toContain("£35,200.00");
    expect(container.textContent).toContain(
      "Scenario-specific predicted revenue outturn",
    );

    await act(async () => {
      root.unmount();
    });
    queryClient.clear();
  });
});
