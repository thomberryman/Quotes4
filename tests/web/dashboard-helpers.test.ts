import { describe, expect, it } from "vitest";

import {
  getConfidenceBandLabel,
  getDefaultDashboardFilters,
  parseDashboardFilters,
  serializeDashboardFilters,
} from "../../apps/web/features/dashboard/dashboard-helpers";

describe("dashboard filter helpers", () => {
  it("serializes explicit dashboard filters into a stable query string", () => {
    expect(
      serializeDashboardFilters({
        fromMonth: "2026-01",
        toMonth: "2026-06",
        clientId: "client_aurora",
        projectId: "project_blue_echo",
        disciplineId: "grade",
        status: "complete",
      }),
    ).toBe(
      "fromMonth=2026-01&toMonth=2026-06&clientId=client_aurora&projectId=project_blue_echo&disciplineId=grade&status=complete",
    );
  });

  it("parses URL filters and falls back to the default dashboard window", () => {
    expect(
      parseDashboardFilters(
        "clientId=client_bbc&status=awarded",
        new Date("2026-03-31T12:00:00Z"),
      ),
    ).toEqual({
      fromMonth: "2025-10",
      toMonth: "2026-09",
      clientId: "client_bbc",
      projectId: undefined,
      disciplineId: undefined,
      status: "awarded",
    });

    expect(
      getDefaultDashboardFilters(new Date("2026-03-31T12:00:00Z")),
    ).toEqual({
      fromMonth: "2025-10",
      toMonth: "2026-09",
    });
  });
});

describe("confidence labels", () => {
  it("maps confidence bands to user-facing labels", () => {
    expect(getConfidenceBandLabel("high")).toBe("High");
    expect(getConfidenceBandLabel("medium")).toBe("Medium");
    expect(getConfidenceBandLabel("low")).toBe("Low");
    expect(getConfidenceBandLabel("watch")).toBe("watch");
  });
});
