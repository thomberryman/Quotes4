import type {
  ActualMappingApprovalAction,
  ActualsImportRowRead,
  CetaImportStatus,
  CetaRowFinancialType,
} from "@quotes4/contracts";

export interface CetaDecisionDraft {
  mappedProjectId: string;
  mappedDisciplineId: string;
  financialType: CetaRowFinancialType;
  costCategoryKey: string;
  revenueCategoryKey: string;
  approvalAction: ActualMappingApprovalAction;
  reviewerNote: string;
}

function emptyString(value?: string | null) {
  return value ?? "";
}

export function buildDecisionDraft(
  row: ActualsImportRowRead,
  batchProjectId?: string | null,
): CetaDecisionDraft {
  return {
    mappedProjectId: emptyString(
      row.latestDecision?.mappedProjectId ?? row.suggestedProjectId ?? batchProjectId,
    ),
    mappedDisciplineId: emptyString(
      row.latestDecision?.mappedDisciplineId ?? row.suggestedDisciplineId,
    ),
    financialType: row.latestDecision?.financialType ?? row.financialType ?? "cost",
    costCategoryKey: emptyString(
      row.latestDecision?.costCategoryKey ?? row.suggestedCostCategoryKey,
    ),
    revenueCategoryKey: emptyString(
      row.latestDecision?.revenueCategoryKey ?? row.suggestedRevenueCategoryKey,
    ),
    approvalAction:
      row.latestDecision?.approvalAction ??
      (row.matchedCurrentActualId ? "link_existing" : "post_new"),
    reviewerNote: emptyString(row.latestDecision?.reviewerNote),
  };
}

export function resolveSelectedRowId(
  rows: ActualsImportRowRead[],
  selectedRowId: string,
): string {
  if (rows.some((row) => row.id === selectedRowId)) {
    return selectedRowId;
  }

  return rows[0]?.id ?? "";
}

export function canProcessBatch(status: CetaImportStatus) {
  return ["uploaded", "failed"].includes(status);
}

export function canApproveBatch(status: CetaImportStatus) {
  return status === "in_review";
}

export function canRejectBatch(status: CetaImportStatus) {
  return ["uploaded", "in_review", "failed"].includes(status);
}
