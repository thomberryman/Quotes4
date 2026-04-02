// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ProjectPredictiveGuidanceResponse,
  QuoteRead,
  QuoteVersionRead,
} from "@quotes4/contracts";

import { QuoteBuilderWorkspace } from "../../apps/web/components/features/quotes/quote-builder-workspace";

const apiClient = {
  createQuote: vi.fn(),
  createQuoteVersion: vi.fn(),
  getProjectPredictiveGuidance: vi.fn(),
  getQuote: vi.fn(),
  getQuoteVersion: vi.fn(),
  issueQuoteVersion: vi.fn(),
  listDisciplines: vi.fn(),
  updateQuote: vi.fn(),
  updateQuoteVersion: vi.fn(),
};

vi.mock("@/lib/api/browser-client", () => ({
  getBrowserApiClient: () => apiClient,
}));

// React 18 tests need this flag for act() coverage when using createRoot directly.
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function buildQuote(): QuoteRead {
  return {
    id: "quote_alpha",
    projectId: "project_alpha",
    quoteNumber: "Q-001",
    title: "Alpha Quote",
    currentVersionId: "version_1",
    currentVersionStatus: "draft",
    updatedAt: "2026-04-01T12:00:00Z",
    versions: [
      {
        id: "version_1",
        quoteId: "quote_alpha",
        versionNumber: 1,
        status: "draft",
        title: "Version 1",
        currencyCode: "GBP",
        totalAmount: 120000,
        updatedAt: "2026-04-01T12:00:00Z",
      },
      {
        id: "version_2",
        quoteId: "quote_alpha",
        versionNumber: 2,
        status: "draft",
        title: "Version 2",
        currencyCode: "GBP",
        totalAmount: 140000,
        updatedAt: "2026-04-02T12:00:00Z",
      },
    ],
  } as QuoteRead;
}

function buildVersion(versionId: string): QuoteVersionRead {
  const versionNumber = versionId === "version_2" ? 2 : 1;
  return {
    id: versionId,
    quoteId: "quote_alpha",
    versionNumber,
    status: "draft",
    title: `Version ${versionNumber}`,
    currencyCode: "GBP",
    sourceVersionLabel: null,
    sourceDocumentDate: null,
    clientFacingNotes: null,
    internalNotes: null,
    pricingContext: null,
    subtotalAmount: versionId === "version_2" ? 140000 : 120000,
    taxAmount: 0,
    totalAmount: versionId === "version_2" ? 140000 : 120000,
    sections: [],
    issuedAt: null,
    updatedAt: versionId === "version_2"
      ? "2026-04-02T12:00:00Z"
      : "2026-04-01T12:00:00Z",
  } as QuoteVersionRead;
}

function buildGuidance(
  versionId: string,
  median: number,
): ProjectPredictiveGuidanceResponse {
  return {
    id: `prediction_${versionId}`,
    projectId: "project_alpha",
    quoteVersionId: versionId,
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
    methodologySummary: "Comparable guidance for the active quote version.",
    generatedAt: "2026-04-01T12:00:00Z",
    createdAt: "2026-04-01T12:00:00Z",
    updatedAt: "2026-04-01T12:00:00Z",
    target: {
      projectId: "project_alpha",
      projectName: "Project Alpha",
      quoteVersionId: versionId,
      quoteCurrencyCode: "GBP",
    },
    modelInfo: {
      comparableProjectsUsed: 3,
      completeActualHistoryCount: 2,
      monthlyProfileCount: 2,
      updateApproach: "Deterministic comparable blend.",
      refreshedAt: "2026-04-01T12:00:00Z",
    },
    comparableQuoteRange: null,
    actualInformedQuoteRange: null,
    likelyQuoteRange: {
      basis: "actual_informed_history",
      confidence: "high",
      currencyCode: "GBP",
      low: median - 10000,
      median,
      high: median + 10000,
      acceptanceStatus: "pending_review",
    },
    disciplineUsage: [
      {
        disciplineId: "discipline_offline",
        disciplineCode: "offline",
        disciplineName: "Offline",
        usageRatePct: 95,
        predictedSharePct: 40,
        predictedAmountMedian: median * 0.4,
        predictedAmountLow: median * 0.35,
        predictedAmountHigh: median * 0.45,
        observedVarianceMedianPct: 6,
        confidence: "high",
        isTargetDiscipline: true,
        sampleSize: 3,
      },
    ],
    monthlyRevenueSpread: [],
    overrunRisk: {
      level: "medium",
      flags: [],
    },
    riskSignals: [],
    winProbability: null,
    scenarios: [],
    topComparables: [
      {
        projectId: "project_comp_1",
        projectName: "Comparable One",
      },
    ],
    moduleOutputs: [],
    overrides: [],
    evaluations: [],
    missingCriticalInputs: [],
    featureSnapshot: {},
    requestContext: {
      quoteVersionId: versionId,
      limit: 10,
    },
    sourceReferences: [],
  } as ProjectPredictiveGuidanceResponse;
}

async function flushEffects() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  });
}

type RenderedWorkspace = {
  container: HTMLDivElement;
  queryClient: QueryClient;
  root: Root;
};

async function renderWorkspace(): Promise<RenderedWorkspace> {
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
        <QuoteBuilderWorkspace
          projectId="project_alpha"
          projectName="Project Alpha"
          quotes={[
            {
              id: "quote_alpha",
              projectId: "project_alpha",
              quoteNumber: "Q-001",
              title: "Alpha Quote",
              currentVersionId: "version_1",
              currentVersionStatus: "draft",
              updatedAt: "2026-04-01T12:00:00Z",
            },
          ]}
          initialSelectedVersionId="version_1"
          initialPredictiveGuidance={buildGuidance("version_1", 120000)}
        />
      </QueryClientProvider>,
    );
  });

  await flushEffects();

  return { container, queryClient, root };
}

describe("QuoteBuilderWorkspace", () => {
  beforeEach(() => {
    apiClient.getQuote.mockResolvedValue(buildQuote());
    apiClient.getQuoteVersion.mockImplementation(async (versionId: string) =>
      buildVersion(versionId),
    );
    apiClient.getProjectPredictiveGuidance.mockImplementation(
      async (_projectId: string, options?: { quoteVersionId?: string }) =>
        buildGuidance(
          options?.quoteVersionId ?? "version_1",
          options?.quoteVersionId === "version_2" ? 140000 : 120000,
        ),
    );
    apiClient.listDisciplines.mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("renders advisory comparable guidance and refreshes it when the selected quote version changes", async () => {
    const { container, queryClient, root } = await renderWorkspace();

    expect(container.textContent).toContain("Comparable quote guidance");
    expect(container.textContent).toContain("£120,000");
    expect(apiClient.getProjectPredictiveGuidance).toHaveBeenCalledWith(
      "project_alpha",
      expect.objectContaining({
        limit: 10,
        quoteVersionId: "version_1",
      }),
    );

    const selects = container.querySelectorAll("select");
    const versionSelect = selects[1] as HTMLSelectElement;

    await act(async () => {
      versionSelect.value = "version_2";
      versionSelect.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await flushEffects();

    expect(apiClient.getProjectPredictiveGuidance).toHaveBeenCalledWith(
      "project_alpha",
      expect.objectContaining({
        limit: 10,
        quoteVersionId: "version_2",
      }),
    );
    expect(container.textContent).toContain("£140,000");

    await act(async () => {
      root.unmount();
    });
    queryClient.clear();
  });
});
