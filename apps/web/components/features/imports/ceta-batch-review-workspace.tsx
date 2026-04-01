"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  ActualMappingApprovalAction,
  ActualsImportBatchDetailRead,
  ActualsImportRowListResponse,
  CetaRowFinancialType,
  DisciplineListResponse,
  ProjectListResponse,
} from "@quotes4/contracts";
import { ApiClientError } from "@quotes4/contracts";

import { CheckboxField } from "@/components/forms/checkbox-field";
import { SelectField } from "@/components/forms/select-field";
import { TextAreaField } from "@/components/forms/text-area-field";
import { TextInput } from "@/components/forms/text-input";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SummaryStat } from "@/components/ui/summary-stat";
import { getBrowserApiClient } from "@/lib/api/browser-client";
import { formatCurrency, formatDate, formatStatusLabel } from "@/lib/format";
import { queryKeys } from "@/lib/query/keys";
import {
  buildDecisionDraft,
  canApproveBatch,
  canProcessBatch,
  canRejectBatch,
  resolveSelectedRowId,
} from "./ceta-review-helpers";

export function CetaBatchReviewWorkspace({
  batchId,
  initialBatch,
  initialRows,
  initialProjects,
  initialDisciplines,
}: {
  batchId: string;
  initialBatch: ActualsImportBatchDetailRead;
  initialRows: ActualsImportRowListResponse;
  initialProjects: ProjectListResponse;
  initialDisciplines: DisciplineListResponse;
}) {
  const api = getBrowserApiClient();
  const queryClient = useQueryClient();
  const [reviewQueue, setReviewQueue] = useState<string | null>(null);
  const [selectedRowId, setSelectedRowId] = useState(initialRows.items[0]?.id ?? "");
  const [mappedProjectId, setMappedProjectId] = useState("");
  const [mappedDisciplineId, setMappedDisciplineId] = useState("");
  const [financialType, setFinancialType] =
    useState<CetaRowFinancialType>("cost");
  const [costCategoryKey, setCostCategoryKey] = useState("");
  const [revenueCategoryKey, setRevenueCategoryKey] = useState("");
  const [approvalAction, setApprovalAction] =
    useState<ActualMappingApprovalAction>("post_new");
  const [reviewerNote, setReviewerNote] = useState("");
  const [saveProjectExternalReference, setSaveProjectExternalReference] =
    useState(false);
  const [saveCategoryAlias, setSaveCategoryAlias] = useState(false);
  const [saveRule, setSaveRule] = useState(false);
  const [ruleName, setRuleName] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [withdrawActualIds, setWithdrawActualIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const batchQuery = useQuery({
    initialData: initialBatch,
    queryFn: async () => api.getActualsImportBatch(batchId),
    queryKey: queryKeys.actualsImportBatch(batchId),
  });

  const rowsQuery = useQuery({
    initialData: initialRows,
    queryFn: async () =>
      reviewQueue
        ? api.listActualsImportRows(batchId, { reviewQueue })
        : api.listActualsImportRows(batchId),
    queryKey: queryKeys.actualsImportRows(batchId, reviewQueue),
  });

  useEffect(() => {
    const nextSelectedRowId = resolveSelectedRowId(
      rowsQuery.data.items,
      selectedRowId,
    );

    if (nextSelectedRowId !== selectedRowId) {
      setSelectedRowId(nextSelectedRowId);
    }
  }, [rowsQuery.data.items, selectedRowId]);

  const selectedRow =
    rowsQuery.data.items.find((row) => row.id === selectedRowId) ?? null;

  useEffect(() => {
    if (!selectedRow) {
      return;
    }

    const draft = buildDecisionDraft(selectedRow, batchQuery.data.projectId);

    setMappedProjectId(draft.mappedProjectId);
    setMappedDisciplineId(draft.mappedDisciplineId);
    setFinancialType(draft.financialType);
    setCostCategoryKey(draft.costCategoryKey);
    setRevenueCategoryKey(draft.revenueCategoryKey);
    setApprovalAction(draft.approvalAction);
    setReviewerNote(draft.reviewerNote);
    setSaveProjectExternalReference(false);
    setSaveCategoryAlias(false);
    setSaveRule(false);
    setRuleName("");
  }, [batchQuery.data.projectId, selectedRow]);

  useEffect(() => {
    setWithdrawActualIds([]);
  }, [batchQuery.data.snapshotWithdrawalCandidates]);

  const processMutation = useMutation({
    mutationFn: async () => api.processActualsImportBatch(batchId),
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not queue the CETA parse job.",
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.actualsImportBatch(batchId),
      });
    },
  });

  const decisionMutation = useMutation({
    mutationFn: async () => {
      if (!selectedRow) {
        throw new Error("Choose a row before saving a decision.");
      }

      return api.updateActualsImportRowDecision(selectedRow.id, {
        mappedProjectId: mappedProjectId || null,
        mappedDisciplineId: mappedDisciplineId || null,
        financialType: financialType || null,
        costCategoryKey: costCategoryKey || null,
        revenueCategoryKey: revenueCategoryKey || null,
        approvalAction,
        matchedExistingActualId: selectedRow.matchedCurrentActualId ?? null,
        reviewerNote: reviewerNote || null,
        saveProjectExternalReference,
        saveCategoryAlias,
        saveRule,
        ruleName: ruleName || null,
      });
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError || caughtError instanceof Error
          ? caughtError.message
          : "Could not save the row decision.",
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.actualsImportRows(batchId, reviewQueue),
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.actualsImportBatch(batchId),
      });
    },
  });

  const approveMutation = useMutation({
    mutationFn: async () =>
      api.approveActualsImportBatch(batchId, {
        withdrawActualIds,
      }),
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not approve the CETA batch.",
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.actualsImportRows(batchId, reviewQueue),
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.actualsImportBatch(batchId),
      });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: async () =>
      api.rejectActualsImportBatch(batchId, { reason: rejectReason || null }),
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not reject the CETA batch.",
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.actualsImportBatch(batchId),
      });
    },
  });

  function applyCandidate(targetKey: string, dimension: string) {
    if (dimension === "project") {
      setMappedProjectId(targetKey);
    }
    if (dimension === "discipline") {
      setMappedDisciplineId(targetKey);
    }
    if (dimension === "cost_category") {
      setCostCategoryKey(targetKey);
      setFinancialType("cost");
    }
    if (dimension === "revenue_category") {
      setRevenueCategoryKey(targetKey);
      setFinancialType("revenue");
    }
    if (dimension === "financial_type") {
      setFinancialType(targetKey as CetaRowFinancialType);
    }
  }

  function toggleWithdrawal(actualId: string) {
    setWithdrawActualIds((current) =>
      current.includes(actualId)
        ? current.filter((value) => value !== actualId)
        : [...current, actualId],
    );
  }

  return (
    <div className="space-y-6">
      {error ? <ErrorState title="CETA workflow error" description={error} /> : null}

      <div className="grid gap-4 md:grid-cols-4">
        <SummaryStat label="Status" value={formatStatusLabel(batchQuery.data.status)} />
        <SummaryStat
          label="Rows staged"
          value={String(batchQuery.data.rowCount)}
        />
        <SummaryStat
          label="Blocking issues"
          value={String(batchQuery.data.blockingIssueCount)}
        />
        <SummaryStat
          label="Coverage"
          value={`${batchQuery.data.coverageMode} · ${formatDate(
            batchQuery.data.coverageStart,
          )}`}
        />
      </div>

      <SectionCard
        title="Batch Control"
        description="Queue parsing, review the current batch status, and perform terminal batch actions."
        actions={<StatusBadge value={batchQuery.data.status} />}
      >
        <div className="flex flex-wrap gap-3">
          <Button
            disabled={!canProcessBatch(batchQuery.data.status) || processMutation.isPending}
            onClick={() => processMutation.mutate()}
            type="button"
            variant="primary"
          >
            {processMutation.isPending ? "Queuing..." : "Start parse"}
          </Button>
          <Button
            disabled={!canApproveBatch(batchQuery.data.status) || approveMutation.isPending}
            onClick={() => approveMutation.mutate()}
            type="button"
          >
            {approveMutation.isPending ? "Approving..." : "Approve batch"}
          </Button>
          <Button
            disabled={!canRejectBatch(batchQuery.data.status) || rejectMutation.isPending}
            onClick={() => rejectMutation.mutate()}
            type="button"
            variant="danger"
          >
            {rejectMutation.isPending ? "Rejecting..." : "Reject batch"}
          </Button>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <TextAreaField
            label="Reject reason"
            onChange={(event) => setRejectReason(event.target.value)}
            placeholder="Optional reason if the batch should be rejected."
            value={rejectReason}
          />
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
            <p className="font-medium text-slate-900">Source file</p>
            <p className="mt-1">{batchQuery.data.file.fileName}</p>
            <p className="mt-2 text-xs text-slate-500">
              Parser profile: {batchQuery.data.parserProfileDetected ?? "Not detected yet"}
            </p>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Approval Preview"
        description="Compare the staged import against the current quote, forecast, and current approved actuals before approval."
      >
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="space-y-3">
            <p className="text-sm font-medium text-slate-900">Project variances</p>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                <thead>
                  <tr className="text-slate-500">
                    <th className="px-3 py-2 font-medium">Project</th>
                    <th className="px-3 py-2 font-medium">Import</th>
                    <th className="px-3 py-2 font-medium">Quote</th>
                    <th className="px-3 py-2 font-medium">Forecast</th>
                    <th className="px-3 py-2 font-medium">Current actuals</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {batchQuery.data.varianceProjects.map((item) => (
                    <tr key={item.projectId}>
                      <td className="px-3 py-3">{item.projectName}</td>
                      <td className="px-3 py-3">{formatCurrency(item.importAmount)}</td>
                      <td className="px-3 py-3">
                        {item.currentQuoteAmount != null
                          ? formatCurrency(item.currentQuoteAmount)
                          : "Not set"}
                      </td>
                      <td className="px-3 py-3">
                        {item.currentForecastAmount != null
                          ? formatCurrency(item.currentForecastAmount)
                          : "Not set"}
                      </td>
                      <td className="px-3 py-3">
                        {formatCurrency(item.currentActualAmount ?? 0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="space-y-3">
            <p className="text-sm font-medium text-slate-900">Snapshot withdrawals</p>
            {batchQuery.data.snapshotWithdrawalCandidates.length ? (
              <div className="space-y-3">
                {batchQuery.data.snapshotWithdrawalCandidates.map((candidate) => (
                  <div
                    className="rounded-lg border border-slate-200 p-3"
                    key={candidate.actualId}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-medium text-slate-900">{candidate.projectName}</p>
                        <p className="text-sm text-slate-600">
                          {candidate.description ?? "No description"} ·{" "}
                          {formatCurrency(candidate.amount, candidate.currencyCode)}
                        </p>
                      </div>
                      <CheckboxField
                        checked={withdrawActualIds.includes(candidate.actualId)}
                        label="Withdraw on approval"
                        onChange={() => toggleWithdrawal(candidate.actualId)}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-600">
                No snapshot withdrawals are currently suggested for this batch.
              </p>
            )}
          </div>
        </div>
      </SectionCard>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <SectionCard
          title="Row Queue"
          description="Filter the staged rows by review queue and choose a row to inspect or edit."
          actions={
            <SelectField
              className="min-w-44"
              onChange={(event) =>
                setReviewQueue(event.target.value ? event.target.value : null)
              }
              value={reviewQueue ?? ""}
            >
              <option value="">All queues</option>
              {batchQuery.data.reviewBuckets.map((bucket) => (
                <option key={bucket.key} value={bucket.key}>
                  {bucket.label} ({bucket.count})
                </option>
              ))}
            </SelectField>
          }
        >
          <div className="space-y-2">
            {rowsQuery.data.items.map((row) => (
              <button
                className={`w-full rounded-lg border px-4 py-3 text-left transition ${
                  row.id === selectedRowId
                    ? "border-slate-900 bg-slate-50"
                    : "border-slate-200 hover:bg-slate-50"
                }`}
                key={row.id}
                onClick={() => setSelectedRowId(row.id)}
                type="button"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-slate-900">
                      Row {row.rowNumber} · {row.description ?? "No description"}
                    </p>
                    <p className="mt-1 text-sm text-slate-600">
                      {row.vendorName ?? "No vendor"} ·{" "}
                      {formatCurrency(row.amount, row.currencyCode)}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      Suggested project: {row.suggestedProjectName ?? "Not matched"}
                    </p>
                  </div>
                  <StatusBadge value={row.reviewQueue} />
                </div>
              </button>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Row Review"
          description="Accept suggestions, override dimensions, or mark the row as a repeat, correction, or rejection."
        >
          {selectedRow ? (
            <div className="space-y-4">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                <p className="font-medium text-slate-900">
                  {selectedRow.description ?? "No description"}
                </p>
                <p className="mt-1">
                  {selectedRow.vendorName ?? "No vendor"} ·{" "}
                  {formatCurrency(selectedRow.amount, selectedRow.currencyCode)}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Work date: {formatDate(selectedRow.workDate)}
                </p>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <SelectField
                  label="Mapped project"
                  onChange={(event) => setMappedProjectId(event.target.value)}
                  value={mappedProjectId}
                >
                  <option value="">Choose a project</option>
                  {initialProjects.items.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </SelectField>
                <SelectField
                  label="Mapped discipline"
                  onChange={(event) => setMappedDisciplineId(event.target.value)}
                  value={mappedDisciplineId}
                >
                  <option value="">No discipline</option>
                  {initialDisciplines.items.map((discipline) => (
                    <option key={discipline.id} value={discipline.id}>
                      {discipline.name}
                    </option>
                  ))}
                </SelectField>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <SelectField
                  label="Financial type"
                  onChange={(event) =>
                    setFinancialType(event.target.value as CetaRowFinancialType)
                  }
                  value={financialType}
                >
                  <option value="cost">Cost</option>
                  <option value="revenue">Revenue</option>
                  <option value="review_required">Review required</option>
                </SelectField>
                <SelectField
                  label="Approval action"
                  onChange={(event) =>
                    setApprovalAction(
                      event.target.value as ActualMappingApprovalAction,
                    )
                  }
                  value={approvalAction}
                >
                  <option value="post_new">Post new</option>
                  <option
                    disabled={!selectedRow.matchedCurrentActualId}
                    value="link_existing"
                  >
                    Link existing repeat
                  </option>
                  <option
                    disabled={!selectedRow.matchedCurrentActualId}
                    value="supersede_existing"
                  >
                    Supersede existing
                  </option>
                  <option value="reject">Reject row</option>
                </SelectField>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <TextInput
                  label="Cost category key"
                  onChange={(event) => setCostCategoryKey(event.target.value)}
                  placeholder="editorial_labor"
                  value={costCategoryKey}
                />
                <TextInput
                  label="Revenue category key"
                  onChange={(event) => setRevenueCategoryKey(event.target.value)}
                  placeholder="editorial_services"
                  value={revenueCategoryKey}
                />
              </div>

              <TextAreaField
                label="Reviewer note"
                onChange={(event) => setReviewerNote(event.target.value)}
                placeholder="Why this row was approved, linked, corrected, or rejected."
                value={reviewerNote}
              />

              <div className="grid gap-2 md:grid-cols-2">
                <CheckboxField
                  checked={saveProjectExternalReference}
                  label="Save project external reference"
                  onChange={(event) =>
                    setSaveProjectExternalReference(event.target.checked)
                  }
                />
                <CheckboxField
                  checked={saveCategoryAlias}
                  label="Save alias from this correction"
                  onChange={(event) => setSaveCategoryAlias(event.target.checked)}
                />
                <CheckboxField
                  checked={saveRule}
                  label="Save reusable rule"
                  onChange={(event) => setSaveRule(event.target.checked)}
                />
                <TextInput
                  label="Rule name"
                  onChange={(event) => setRuleName(event.target.value)}
                  placeholder="Optional rule label"
                  value={ruleName}
                />
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium text-slate-900">Candidate suggestions</p>
                <div className="flex flex-wrap gap-2">
                  {selectedRow.candidates.map((candidate) => (
                    <button
                      className="rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-50"
                      key={candidate.id}
                      onClick={() =>
                        applyCandidate(candidate.targetKey, candidate.dimension)
                      }
                      type="button"
                    >
                      {candidate.dimension.replace(/_/g, " ")} · {candidate.targetLabel}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium text-slate-900">Issues</p>
                {selectedRow.issues.length ? (
                  <div className="space-y-2">
                    {selectedRow.issues.map((issue) => (
                      <div
                        className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
                        key={issue.id}
                      >
                        <p className="font-medium">{issue.issueCode}</p>
                        <p className="mt-1">{issue.message}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-slate-600">No row-level issues on this record.</p>
                )}
              </div>

              <Button
                onClick={() => decisionMutation.mutate()}
                type="button"
                variant="primary"
              >
                {decisionMutation.isPending ? "Saving..." : "Save decision"}
              </Button>
            </div>
          ) : (
            <p className="text-sm text-slate-600">
              Choose a staged row to review its candidates, issues, and approval action.
            </p>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
