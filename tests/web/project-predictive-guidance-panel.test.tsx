// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import type { ProjectPredictiveGuidanceResponse } from "@quotes4/contracts";

import { ProjectPredictiveGuidancePanel } from "../../apps/web/components/features/projects/project-predictive-guidance-panel";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function buildGuidance(): ProjectPredictiveGuidanceResponse {
  return {
    id: "prediction_1",
    projectId: "project_1",
    modelVersion: "v1",
    strategyKey: "deterministic",
    maturityStage: "stage_2",
    primaryEvidenceSource: "comparables",
    fallbackTier: "high_similarity_history",
    featureReadinessScore: 84,
    dataSufficiencyScore: 78,
    confidenceScore: 75,
    confidenceLabel: "high",
    expectedScenarioKey: "base",
    methodologySummary: "Comparable-derived prediction with advisory spend.",
    generatedAt: "2026-04-01T12:00:00Z",
    createdAt: "2026-04-01T12:00:00Z",
    updatedAt: "2026-04-01T12:00:00Z",
    target: {
      projectId: "project_1",
      projectName: "Project 1",
      quoteCurrencyCode: "GBP",
    },
    modelInfo: {
      strategy: "deterministic",
      refreshedAt: "2026-04-01T12:00:00Z",
      updateApproach: "Deterministic modular prediction",
      comparableProjectsConsidered: 5,
      comparableProjectsUsed: 3,
      completeActualHistoryCount: 3,
      monthlyProfileCount: 3,
    },
    disciplineUsage: [],
    monthlyRevenueSpread: [],
    overrunRisk: { level: "low", flags: [] },
    riskSignals: [],
    scenarios: [
      {
        scenarioKey: "base",
        title: "Base",
        overrunRisk: { level: "low", flags: [] },
        spendSummary: {
          currentActualCost: 10000,
          predictedTotalCost: 80000,
          predictedRemainingCost: 70000,
          impliedMarginAmount: 20000,
          impliedMarginPct: 20,
          confidence: "medium",
          confidenceScore: 66,
          fallbackTier: "high_similarity_history",
          basis: "comparables_with_current_actuals_floor",
          disciplineSpend: [],
        },
      },
    ],
    topComparables: [],
    moduleOutputs: [],
    overrides: [],
    evaluations: [],
    sourceReferences: [],
  } as ProjectPredictiveGuidanceResponse;
}

describe("ProjectPredictiveGuidancePanel", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("renders advisory predicted spend separately from revenue guidance", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root: Root = createRoot(container);

    await act(async () => {
      root.render(<ProjectPredictiveGuidancePanel predictiveGuidance={buildGuidance()} />);
    });

    expect(container.textContent).toContain("Advisory Predicted Spend");
    expect(container.textContent).toContain("Predicted total spend");
    expect(container.textContent).toContain("Implied margin (advisory)");

    await act(async () => {
      root.unmount();
    });
  });
});
