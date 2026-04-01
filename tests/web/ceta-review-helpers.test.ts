import { describe, expect, it } from "vitest";

import type { ActualsImportRowRead } from "@quotes4/contracts";

import {
  buildDecisionDraft,
  canApproveBatch,
  canProcessBatch,
  canRejectBatch,
  resolveSelectedRowId,
} from "../../apps/web/components/features/imports/ceta-review-helpers";

function makeRow(overrides: Partial<ActualsImportRowRead> = {}): ActualsImportRowRead {
  return {
    id: "row-1",
    rowNumber: 1,
    sourceRowUid: null,
    status: "unmatched",
    reviewQueue: "blocking",
    externalProjectCode: "PRJ-001",
    workDate: "2026-03-01",
    postingDate: "2026-03-02",
    sourceDisciplineCode: "edit",
    description: "Editorial labor",
    vendorName: "Vendor Co",
    amount: 1200,
    currencyCode: "GBP",
    financialType: "cost",
    rowHash: "row-hash",
    businessKeyHash: "business-key",
    duplicateGroupKey: null,
    suggestedProjectId: null,
    suggestedProjectName: null,
    suggestedDisciplineId: null,
    suggestedDisciplineName: null,
    suggestedCostCategoryKey: null,
    suggestedRevenueCategoryKey: null,
    matchedCurrentActualId: null,
    issues: [],
    candidates: [],
    latestDecision: null,
    rawPayload: null,
    ...overrides,
  };
}

describe("ceta review helpers", () => {
  it("builds a review draft from the latest decision before falling back to suggestions", () => {
    const row = makeRow({
      suggestedProjectId: "project-suggested",
      suggestedDisciplineId: "discipline-suggested",
      suggestedCostCategoryKey: "labor",
      latestDecision: {
        id: "decision-1",
        mappedProjectId: "project-final",
        mappedProjectName: "Project Final",
        mappedDisciplineId: "discipline-final",
        mappedDisciplineName: "Discipline Final",
        financialType: "revenue",
        costCategoryKey: "ignored",
        revenueCategoryKey: "services",
        approvalAction: "supersede_existing",
        mappingMethod: "manual",
        matchedExistingActualId: "actual-1",
        confidenceScore: 0.99,
        reviewerNote: "Corrected against contract.",
        explanation: null,
        createdRuleId: null,
        createdAliasId: null,
        createdExternalReferenceId: null,
        createdAt: "2026-03-31T10:00:00Z",
      },
    });

    expect(buildDecisionDraft(row, "project-batch")).toEqual({
      mappedProjectId: "project-final",
      mappedDisciplineId: "discipline-final",
      financialType: "revenue",
      costCategoryKey: "ignored",
      revenueCategoryKey: "services",
      approvalAction: "supersede_existing",
      reviewerNote: "Corrected against contract.",
    });
  });

  it("defaults repeat rows to link existing when there is no saved decision", () => {
    const row = makeRow({
      matchedCurrentActualId: "actual-repeat",
      suggestedCostCategoryKey: "editorial_labor",
    });

    expect(buildDecisionDraft(row, "project-batch")).toEqual({
      mappedProjectId: "project-batch",
      mappedDisciplineId: "",
      financialType: "cost",
      costCategoryKey: "editorial_labor",
      revenueCategoryKey: "",
      approvalAction: "link_existing",
      reviewerNote: "",
    });
  });

  it("keeps the selected row when it survives filtering and otherwise falls back to the first row", () => {
    const rows = [makeRow({ id: "row-1" }), makeRow({ id: "row-2" })];

    expect(resolveSelectedRowId(rows, "row-2")).toBe("row-2");
    expect(resolveSelectedRowId(rows, "missing-row")).toBe("row-1");
    expect(resolveSelectedRowId([], "missing-row")).toBe("");
  });

  it("exposes the batch action state used by the approval controls", () => {
    expect(canProcessBatch("uploaded")).toBe(true);
    expect(canProcessBatch("failed")).toBe(true);
    expect(canProcessBatch("in_review")).toBe(false);

    expect(canApproveBatch("in_review")).toBe(true);
    expect(canApproveBatch("approved")).toBe(false);

    expect(canRejectBatch("uploaded")).toBe(true);
    expect(canRejectBatch("in_review")).toBe(true);
    expect(canRejectBatch("failed")).toBe(true);
    expect(canRejectBatch("approved")).toBe(false);
  });
});
