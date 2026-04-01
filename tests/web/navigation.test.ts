import { describe, expect, it } from "vitest";

import {
  flattenNav,
  isNavItemActive,
} from "../../apps/web/lib/navigation/active";
import {
  navigationGroups,
  projectWorkspaceLinks,
} from "../../apps/web/lib/navigation/routes";

describe("navigation helpers", () => {
  it("marks nested project routes as active for their section", () => {
    expect(isNavItemActive("/projects/project-1/forecast", "/projects")).toBe(
      true,
    );
    expect(isNavItemActive("/clients", "/projects")).toBe(false);
  });

  it("flattens nav groups without losing items", () => {
    const items = flattenNav(navigationGroups);
    expect(items.some((item) => item.href === "/dashboard")).toBe(true);
    expect(items.some((item) => item.href === "/projects")).toBe(true);
  });

  it("keeps the actuals workspace available as a live project tab", () => {
    const actualsLink = projectWorkspaceLinks.find(
      (item) => item.href === "actuals-vs-quote",
    );
    expect(actualsLink).toBeDefined();
    expect(actualsLink?.label).toBe("Quote vs Actual");
  });

  it("exposes the scenario planning workspace in project navigation", () => {
    const scenarioLink = projectWorkspaceLinks.find(
      (item) => item.href === "scenarios",
    );
    expect(scenarioLink).toBeDefined();
    expect(scenarioLink?.label).toBe("Scenarios");
  });
});
