// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ForecastPhasingWorkspaceRead } from "@quotes4/contracts";
import { ApiClientError } from "@quotes4/contracts";

import { RevenuePhasingWorkspace } from "../../apps/web/components/features/forecasts/revenue-phasing-workspace";

const routerReplace = vi.fn();
const apiClient = {
  discardProjectForecastPhasingDraft: vi.fn(),
  getForecastPhasingWorkspace: vi.fn(),
  previewForecastPhasingAction: vi.fn(),
  updateProjectForecastPhasingDraft: vi.fn(),
  updateProjectForecastPhasing: vi.fn(),
};

vi.mock("next/navigation", () => ({
  usePathname: () => "/projects/phasing",
  useRouter: () => ({
    replace: routerReplace,
  }),
  useSearchParams: () =>
    new URLSearchParams(
      "fromMonth=2026-06&toMonth=2026-08&rowMode=project&scenarioKey=base",
    ),
}));

vi.mock("@/lib/api/browser-client", () => ({
  getBrowserApiClient: () => apiClient,
}));

function buildWorkspace(options?: {
  activeDraft?: ForecastPhasingWorkspaceRead["rows"][number]["activeDraft"];
  includeSecondRow?: boolean;
}): ForecastPhasingWorkspaceRead {
  const activeDraft = options?.activeDraft ?? null;
  return {
    generatedAt: "2026-04-01T12:00:00Z",
    fromMonth: "2026-06",
    toMonth: "2026-08",
    rowMode: "project",
    scenarioKey: "base",
    filterOptions: {
      clients: [],
      projects: [],
      disciplines: [],
      statuses: [],
      scenarios: [{ id: "base", label: "Base" }],
    },
    months: ["2026-06", "2026-07", "2026-08"],
    rows: [
      {
        rowKey: "project:project_alpha:all",
        rowMode: "project",
        projectId: "project_alpha",
        projectName: "Project Alpha",
        clientId: "client_alpha",
        clientName: "Client Alpha",
        status: "bid",
        forecastVersionId: "forecast_version_alpha",
        forecastVersionStatus: "draft",
        forecastVersionUpdatedAt: "2026-04-01T10:00:00Z",
        scenarioKey: "base",
        currencyCode: "GBP",
        basePhasingProfile: "flat_equal",
        executionStartDate: "2026-06-01",
        executionEndDate: "2026-08-31",
        totalAmount: 9000,
        weightedTotalAmount: 5400,
        canEdit: true,
        activeDraft,
        cells: [
          {
            month: "2026-06",
            amount: 3000,
            weightedAmount: 1800,
            allocationSource: "forecast",
            isManualOverride: false,
            isLocked: false,
            editable: true,
            manualNote: null,
            actualAmount: null,
            lowAmount: 3000,
            highAmount: 3000,
          },
          {
            month: "2026-07",
            amount: 3000,
            weightedAmount: 1800,
            allocationSource: "forecast",
            isManualOverride: false,
            isLocked: false,
            editable: true,
            manualNote: null,
            actualAmount: null,
            lowAmount: 3000,
            highAmount: 3000,
          },
          {
            month: "2026-08",
            amount: 3000,
            weightedAmount: 1800,
            allocationSource: "forecast",
            isManualOverride: false,
            isLocked: false,
            editable: true,
            manualNote: null,
            actualAmount: null,
            lowAmount: 3000,
            highAmount: 3000,
          },
        ],
      },
      ...(options?.includeSecondRow
        ? [
            {
              rowKey: "project:project_beta:all",
              rowMode: "project",
              projectId: "project_beta",
              projectName: "Project Beta",
              clientId: "client_beta",
              clientName: "Client Beta",
              status: "bid",
              forecastVersionId: "forecast_version_beta",
              forecastVersionStatus: "draft",
              forecastVersionUpdatedAt: "2026-04-01T10:00:00Z",
              scenarioKey: "base",
              currencyCode: "GBP",
              basePhasingProfile: "flat_equal",
              executionStartDate: "2026-06-01",
              executionEndDate: "2026-08-31",
              totalAmount: 9000,
              weightedTotalAmount: 5400,
              canEdit: true,
              activeDraft: null,
              cells: [
                {
                  month: "2026-06",
                  amount: 3000,
                  weightedAmount: 1800,
                  allocationSource: "forecast",
                  isManualOverride: false,
                  isLocked: false,
                  editable: true,
                  manualNote: null,
                  actualAmount: null,
                  lowAmount: 3000,
                  highAmount: 3000,
                },
                {
                  month: "2026-07",
                  amount: 3000,
                  weightedAmount: 1800,
                  allocationSource: "forecast",
                  isManualOverride: false,
                  isLocked: false,
                  editable: true,
                  manualNote: null,
                  actualAmount: null,
                  lowAmount: 3000,
                  highAmount: 3000,
                },
                {
                  month: "2026-08",
                  amount: 3000,
                  weightedAmount: 1800,
                  allocationSource: "forecast",
                  isManualOverride: false,
                  isLocked: false,
                  editable: true,
                  manualNote: null,
                  actualAmount: null,
                  lowAmount: 3000,
                  highAmount: 3000,
                },
              ],
            },
          ]
        : []),
    ],
    monthTotals: [
      { month: "2026-06", amount: 3000, weightedAmount: 1800 },
      { month: "2026-07", amount: 3000, weightedAmount: 1800 },
      { month: "2026-08", amount: 3000, weightedAmount: 1800 },
    ],
    statusMonthTotals: [
      { status: "bid", month: "2026-06", amount: 3000, weightedAmount: 1800 },
      { status: "bid", month: "2026-07", amount: 3000, weightedAmount: 1800 },
      { status: "bid", month: "2026-08", amount: 3000, weightedAmount: 1800 },
    ],
    recentChanges: [],
  };
}

async function flushEffects() {
  await act(async () => {
    await Promise.resolve();
  });
}

function setInputValue(input: HTMLInputElement, value: string) {
  const valueSetter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )?.set;
  valueSetter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

type RenderedWorkspace = {
  container: HTMLDivElement;
  queryClient: QueryClient;
  root: Root;
  workspace: ForecastPhasingWorkspaceRead;
};

function buildDraftResponse(
  workspace: ForecastPhasingWorkspaceRead,
  payload: {
    currentState: {
      forecastVersionId?: string | null;
      expectedUpdatedAt: string;
      reason?: string | null;
      cells: Array<{ month: string; amount: number; isLocked: boolean; note?: string | null }>;
    };
    futureStates?: Array<{
      forecastVersionId?: string | null;
      expectedUpdatedAt: string;
      reason?: string | null;
      cells: Array<{ month: string; amount: number; isLocked: boolean; note?: string | null }>;
    }>;
    pastStates?: Array<{
      forecastVersionId?: string | null;
      expectedUpdatedAt: string;
      reason?: string | null;
      cells: Array<{ month: string; amount: number; isLocked: boolean; note?: string | null }>;
    }>;
    rowMode: string;
    disciplineId?: string | null;
    saveMode?: string;
  },
) {
  return {
    id: "draft_alpha",
    forecastVersionId:
      payload.currentState.forecastVersionId ?? workspace.rows[0].forecastVersionId,
    projectId: workspace.rows[0].projectId,
    rowMode: payload.rowMode,
    disciplineId: payload.disciplineId ?? null,
    saveMode: payload.saveMode ?? "replace",
    currentState: payload.currentState,
    pastStates: payload.pastStates ?? [],
    futureStates: payload.futureStates ?? [],
    updatedById: "user_admin",
    updatedByEmail: "admin@quotes4.dev",
    updatedAt: "2026-04-01T12:15:00Z",
  };
}

async function advanceDraftSync() {
  await act(async () => {
    vi.advanceTimersByTime(200);
    await Promise.resolve();
  });
}

async function renderWorkspace(
  workspace: ForecastPhasingWorkspaceRead = buildWorkspace(),
): Promise<RenderedWorkspace> {
  apiClient.getForecastPhasingWorkspace.mockResolvedValue(workspace);
  apiClient.previewForecastPhasingAction.mockResolvedValue({
    projectId: workspace.rows[0].projectId,
    rowMode: "project",
    action: "equal_split",
    disciplineId: null,
    cells: [],
  });
  apiClient.updateProjectForecastPhasingDraft.mockImplementation(
    async (_projectId, payload) => buildDraftResponse(workspace, payload),
  );
  apiClient.discardProjectForecastPhasingDraft.mockResolvedValue(workspace);
  apiClient.updateProjectForecastPhasing.mockResolvedValue(workspace);

  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <RevenuePhasingWorkspace initialWorkspace={workspace} />
      </QueryClientProvider>,
    );
  });
  await flushEffects();

  return {
    container,
    queryClient,
    root,
    workspace,
  };
}

async function cleanupWorkspace(rendered: RenderedWorkspace) {
  await act(async () => {
    rendered.root.unmount();
  });
  rendered.queryClient.clear();
  rendered.container.remove();
}

beforeEach(() => {
  // React 19 expects this flag when tests drive updates inside act().
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  routerReplace.mockReset();
  apiClient.discardProjectForecastPhasingDraft.mockReset();
  apiClient.getForecastPhasingWorkspace.mockReset();
  apiClient.previewForecastPhasingAction.mockReset();
  apiClient.updateProjectForecastPhasingDraft.mockReset();
  apiClient.updateProjectForecastPhasing.mockReset();
  vi.useFakeTimers();
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.useRealTimers();
});

describe("RevenuePhasingWorkspace", () => {
  it("supports drag fill with undo and redo in the month grid", async () => {
    const rendered = await renderWorkspace();
    const rowKey = rendered.workspace.rows[0].rowKey;
    const juneInput = rendered.container.querySelector<HTMLInputElement>(
      `[data-testid="phasing-input-${rowKey}-2026-06"]`,
    );
    const augustCell = rendered.container
      .querySelector<HTMLInputElement>(
        `[data-testid="phasing-input-${rowKey}-2026-08"]`,
      )
      ?.closest("td");

    expect(juneInput).not.toBeNull();
    expect(augustCell).not.toBeNull();

    await act(async () => {
      juneInput?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushEffects();

    if (!juneInput || !augustCell) {
      throw new Error("Expected phasing grid inputs to render.");
    }

    await act(async () => {
      setInputValue(juneInput, "1000");
    });
    await flushEffects();

    const fillHandle = rendered.container.querySelector<HTMLButtonElement>(
      `[data-testid="phasing-fill-handle-${rowKey}-2026-06"]`,
    );
    expect(fillHandle).not.toBeNull();

    await act(async () => {
      fillHandle?.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    });
    await flushEffects();

    await act(async () => {
      augustCell.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });
    await flushEffects();

    await act(async () => {
      window.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    });
    await flushEffects();

    const julyInput = rendered.container.querySelector<HTMLInputElement>(
      `[data-testid="phasing-input-${rowKey}-2026-07"]`,
    );
    const augustInput = rendered.container.querySelector<HTMLInputElement>(
      `[data-testid="phasing-input-${rowKey}-2026-08"]`,
    );
    expect(julyInput?.value).toBe("1000");
    expect(augustInput?.value).toBe("1000");

    const undoButton = rendered.container.querySelector<HTMLButtonElement>(
      '[data-testid="phasing-undo"]',
    );
    const redoButton = rendered.container.querySelector<HTMLButtonElement>(
      '[data-testid="phasing-redo"]',
    );
    expect(undoButton?.disabled).toBe(false);

    await act(async () => {
      undoButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushEffects();

    expect(juneInput.value).toBe("1000");
    expect(julyInput?.value).toBe("3000");
    expect(augustInput?.value).toBe("3000");

    await act(async () => {
      redoButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushEffects();

    expect(julyInput?.value).toBe("1000");
    expect(augustInput?.value).toBe("1000");

    await cleanupWorkspace(rendered);
  });

  it("restores a persisted shared draft after reload", async () => {
    const workspace = buildWorkspace({
      activeDraft: {
        id: "draft_alpha",
        forecastVersionId: "forecast_version_alpha",
        projectId: "project_alpha",
        rowMode: "project",
        disciplineId: null,
        saveMode: "merge",
        currentState: {
          forecastVersionId: "forecast_version_alpha",
          expectedUpdatedAt: "2026-04-01T10:00:00Z",
          reason: "Shared draft from another operator.",
          cells: [
            { month: "2026-06", amount: 1000, isLocked: true, note: null },
            { month: "2026-07", amount: 2000, isLocked: false, note: null },
          ],
        },
        pastStates: [
          {
            forecastVersionId: "forecast_version_alpha",
            expectedUpdatedAt: "2026-04-01T10:00:00Z",
            reason: "Baseline state.",
            cells: [],
          },
        ],
        futureStates: [],
        updatedById: "user_admin",
        updatedByEmail: "admin@quotes4.dev",
        updatedAt: "2026-04-01T12:15:00Z",
      },
    });
    const rendered = await renderWorkspace(workspace);
    const rowKey = workspace.rows[0].rowKey;

    const juneInput = rendered.container.querySelector<HTMLInputElement>(
      `[data-testid="phasing-input-${rowKey}-2026-06"]`,
    );
    const julyInput = rendered.container.querySelector<HTMLInputElement>(
      `[data-testid="phasing-input-${rowKey}-2026-07"]`,
    );
    const undoButton = rendered.container.querySelector<HTMLButtonElement>(
      '[data-testid="phasing-undo"]',
    );
    const saveModeSelect = rendered.container.querySelector<HTMLSelectElement>(
      '[data-testid="phasing-save-mode"]',
    );

    expect(juneInput?.value).toBe("1000");
    expect(julyInput?.value).toBe("2000");
    expect(undoButton?.disabled).toBe(false);
    expect(saveModeSelect?.value).toBe("merge");
    expect(rendered.container.textContent).toContain("Shared draft from another operator.");

    await cleanupWorkspace(rendered);
  });

  it("merges local edits into the refreshed shared draft after a sync conflict", async () => {
    const workspace = buildWorkspace();
    const refreshedWorkspace = buildWorkspace({
      activeDraft: {
        id: "draft_alpha",
        forecastVersionId: "forecast_version_alpha",
        projectId: "project_alpha",
        rowMode: "project",
        disciplineId: null,
        saveMode: "replace",
        currentState: {
          forecastVersionId: "forecast_version_alpha",
          expectedUpdatedAt: "2026-04-01T10:00:00Z",
          reason: "Shared draft from another operator.",
          cells: [{ month: "2026-07", amount: 2500, isLocked: false, note: null }],
        },
        pastStates: [],
        futureStates: [],
        updatedById: "user_other",
        updatedByEmail: "other.operator@quotes4.dev",
        updatedAt: "2026-04-01T12:30:00Z",
      },
    });
    const rendered = await renderWorkspace(workspace);
    const rowKey = workspace.rows[0].rowKey;
    const juneInput = rendered.container.querySelector<HTMLInputElement>(
      `[data-testid="phasing-input-${rowKey}-2026-06"]`,
    );
    const julyInput = rendered.container.querySelector<HTMLInputElement>(
      `[data-testid="phasing-input-${rowKey}-2026-07"]`,
    );

    expect(juneInput).not.toBeNull();
    expect(julyInput).not.toBeNull();

    if (!juneInput || !julyInput) {
      throw new Error("Expected editable phasing inputs for conflict recovery.");
    }

    apiClient.getForecastPhasingWorkspace.mockResolvedValue(refreshedWorkspace);
    apiClient.updateProjectForecastPhasingDraft
      .mockRejectedValueOnce(
        new ApiClientError(
          "Revenue phasing draft has been updated by another operator.",
          409,
          null,
        ),
      )
      .mockImplementation(async (_projectId, payload) =>
        buildDraftResponse(refreshedWorkspace, payload),
      );

    await act(async () => {
      setInputValue(juneInput, "1000");
    });
    await flushEffects();
    await advanceDraftSync();
    await flushEffects();

    expect(
      rendered.container.querySelector('[data-testid="phasing-conflict-banner"]'),
    ).not.toBeNull();
    expect(rendered.container.textContent).toContain(
      "Shared draft changed before your edits could sync.",
    );
    expect(juneInput.value).toBe("1000");
    expect(julyInput.value).toBe("3000");

    const mergeButton = rendered.container.querySelector<HTMLButtonElement>(
      '[data-testid="phasing-merge-conflict-draft"]',
    );
    expect(mergeButton).not.toBeNull();

    await act(async () => {
      mergeButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushEffects();

    expect(
      rendered.container.querySelector('[data-testid="phasing-conflict-banner"]'),
    ).toBeNull();
    expect(juneInput.value).toBe("1000");
    expect(julyInput.value).toBe("2500");
    expect(apiClient.updateProjectForecastPhasingDraft).toHaveBeenCalledTimes(2);
    expect(apiClient.updateProjectForecastPhasingDraft).toHaveBeenLastCalledWith(
      workspace.rows[0].projectId,
      expect.objectContaining({
        expectedDraftUpdatedAt: "2026-04-01T12:30:00Z",
        currentState: expect.objectContaining({
          cells: expect.arrayContaining([
            expect.objectContaining({ month: "2026-06", amount: 1000 }),
            expect.objectContaining({ month: "2026-07", amount: 2500 }),
          ]),
        }),
      }),
    );

    await cleanupWorkspace(rendered);
  });

  it("supports rectangular paste across rows and months", async () => {
    const workspace = buildWorkspace({ includeSecondRow: true });
    const rendered = await renderWorkspace(workspace);
    const firstRowKey = workspace.rows[0].rowKey;
    const secondRowKey = workspace.rows[1].rowKey;

    const juneInput = rendered.container.querySelector<HTMLInputElement>(
      `[data-testid="phasing-input-${firstRowKey}-2026-06"]`,
    );
    const secondRowJulyInput = rendered.container.querySelector<HTMLInputElement>(
      `[data-testid="phasing-input-${secondRowKey}-2026-07"]`,
    );

    expect(juneInput).not.toBeNull();
    expect(secondRowJulyInput).not.toBeNull();

    if (!juneInput || !secondRowJulyInput) {
      throw new Error("Expected editable phasing inputs for rectangle paste.");
    }

    await act(async () => {
      juneInput.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushEffects();

    await act(async () => {
      secondRowJulyInput.dispatchEvent(
        new MouseEvent("click", { bubbles: true, shiftKey: true }),
      );
    });
    await flushEffects();

    await act(async () => {
      const pasteEvent = new Event("paste", { bubbles: true });
      Object.defineProperty(pasteEvent, "clipboardData", {
        value: {
          getData: () => "1000\t2000\n3000\t4000",
        },
      });
      juneInput.dispatchEvent(pasteEvent);
    });
    await flushEffects();
    await advanceDraftSync();

    expect(juneInput.value).toBe("1000");
    expect(
      rendered.container.querySelector<HTMLInputElement>(
        `[data-testid="phasing-input-${firstRowKey}-2026-07"]`,
      )?.value,
    ).toBe("2000");
    expect(
      rendered.container.querySelector<HTMLInputElement>(
        `[data-testid="phasing-input-${secondRowKey}-2026-06"]`,
      )?.value,
    ).toBe("3000");
    expect(secondRowJulyInput.value).toBe("4000");
    expect(apiClient.updateProjectForecastPhasingDraft).toHaveBeenCalled();

    await cleanupWorkspace(rendered);
  });

  it("keeps the existing selection anchor when shift-click focus lands on another row", async () => {
    const workspace = buildWorkspace({ includeSecondRow: true });
    const rendered = await renderWorkspace(workspace);
    const firstRowKey = workspace.rows[0].rowKey;
    const secondRowKey = workspace.rows[1].rowKey;

    const juneInput = rendered.container.querySelector<HTMLInputElement>(
      `[data-testid="phasing-input-${firstRowKey}-2026-06"]`,
    );
    const secondRowJulyInput = rendered.container.querySelector<HTMLInputElement>(
      `[data-testid="phasing-input-${secondRowKey}-2026-07"]`,
    );

    expect(juneInput).not.toBeNull();
    expect(secondRowJulyInput).not.toBeNull();

    if (!juneInput || !secondRowJulyInput) {
      throw new Error("Expected editable phasing inputs for browser-order selection.");
    }

    await act(async () => {
      juneInput.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushEffects();

    await act(async () => {
      secondRowJulyInput.dispatchEvent(
        new MouseEvent("mousedown", { bubbles: true, shiftKey: true }),
      );
      secondRowJulyInput.focus();
      secondRowJulyInput.dispatchEvent(
        new MouseEvent("click", { bubbles: true, shiftKey: true }),
      );
    });
    await flushEffects();

    await act(async () => {
      const pasteEvent = new Event("paste", { bubbles: true });
      Object.defineProperty(pasteEvent, "clipboardData", {
        value: {
          getData: () => "1000\t2000\n3000\t4000",
        },
      });
      juneInput.dispatchEvent(pasteEvent);
    });
    await flushEffects();

    expect(juneInput.value).toBe("1000");
    expect(
      rendered.container.querySelector<HTMLInputElement>(
        `[data-testid="phasing-input-${firstRowKey}-2026-07"]`,
      )?.value,
    ).toBe("2000");
    expect(
      rendered.container.querySelector<HTMLInputElement>(
        `[data-testid="phasing-input-${secondRowKey}-2026-06"]`,
      )?.value,
    ).toBe("3000");
    expect(secondRowJulyInput.value).toBe("4000");

    await cleanupWorkspace(rendered);
  });

  it("sends merge save mode through the row save payload", async () => {
    const rendered = await renderWorkspace();
    const row = rendered.workspace.rows[0];
    const rowKey = row.rowKey;

    const julyInput = rendered.container.querySelector<HTMLInputElement>(
      `[data-testid="phasing-input-${rowKey}-2026-07"]`,
    );
    const saveModeSelect = rendered.container.querySelector<HTMLSelectElement>(
      '[data-testid="phasing-save-mode"]',
    );
    const saveButton = Array.from(
      rendered.container.querySelectorAll<HTMLButtonElement>("button"),
    ).find((button) => button.textContent?.includes("Save row"));

    expect(julyInput).not.toBeNull();
    expect(saveModeSelect).not.toBeNull();
    expect(saveButton).not.toBeNull();

    if (!julyInput || !saveModeSelect || !saveButton) {
      throw new Error("Expected editable phasing controls to render.");
    }

    await act(async () => {
      setInputValue(julyInput, "2000");
      saveModeSelect.value = "merge";
      saveModeSelect.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await flushEffects();

    await act(async () => {
      saveButton.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushEffects();

    expect(apiClient.updateProjectForecastPhasing).toHaveBeenCalledTimes(1);
    expect(apiClient.updateProjectForecastPhasing).toHaveBeenCalledWith(
      row.projectId,
      expect.objectContaining({
        replaceExistingOverrides: false,
        rowMode: "project",
      }),
    );

    await cleanupWorkspace(rendered);
  });
});
