import type {
  PredictionScenarioRead,
  ProjectPredictiveGuidanceResponse,
} from "@quotes4/contracts";

export function getExpectedScenario(
  predictiveGuidance: ProjectPredictiveGuidanceResponse | null | undefined,
): PredictionScenarioRead | undefined {
  if (!predictiveGuidance?.scenarios?.length) {
    return undefined;
  }

  return (
    predictiveGuidance.scenarios.find(
      (item) => item.scenarioKey === predictiveGuidance.expectedScenarioKey,
    ) ?? predictiveGuidance.scenarios[0]
  );
}

export function getExpectedScenarioSpend(
  predictiveGuidance: ProjectPredictiveGuidanceResponse | null | undefined,
) {
  return getExpectedScenario(predictiveGuidance)?.spendSummary;
}
