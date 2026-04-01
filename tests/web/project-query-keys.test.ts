import { describe, expect, it } from "vitest";

import { queryKeys } from "../../apps/web/lib/query/keys";

describe("project query keys", () => {
  it("stabilizes predictive guidance cache keys by project and discipline focus", () => {
    expect(queryKeys.projectPredictiveGuidance("project-1")).toEqual([
      "project-predictive-guidance",
      "project-1",
      "all",
    ]);

    expect(
      queryKeys.projectPredictiveGuidance("project-1", { disciplineId: "grade" }),
    ).toEqual(["project-predictive-guidance", "project-1", "grade"]);
  });

  it("keeps persisted prediction run queries stable by project and run id", () => {
    expect(queryKeys.predictionRuns("project-1")).toEqual([
      "prediction-runs",
      "project-1",
    ]);

    expect(queryKeys.predictionRun("project-1", "run-1")).toEqual([
      "prediction-run",
      "project-1",
      "run-1",
    ]);
  });
});
