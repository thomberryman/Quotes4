"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiClientError } from "@quotes4/contracts";
import type {
  ProjectSummary,
  QuoteIngestionRunDetail,
  QuoteSummary,
} from "@quotes4/contracts";
import { useEffect, useMemo, useState } from "react";

import { getBrowserApiClient } from "@/lib/api/browser-client";
import {
  formatCurrency,
  formatDate,
  formatDateTime,
  formatStatusLabel,
} from "@/lib/format";
import { queryKeys } from "@/lib/query/keys";

import { InlineActionBar } from "@/components/forms/inline-action-bar";
import { SelectField } from "@/components/forms/select-field";
import { TextAreaField } from "@/components/forms/text-area-field";
import { TextInput } from "@/components/forms/text-input";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SummaryStat } from "@/components/ui/summary-stat";

type EditableFieldDecision = {
  id: string;
  fieldPath: string;
  selectedResultId: string;
  reviewedText: string;
  reviewedAmount: string;
  reviewedDate: string;
  reviewStatus: "pending" | "approved" | "rejected";
  reviewerNote: string;
};

type EditableLineDecision = {
  id: string;
  sortOrder: number;
  sourceResultId: string;
  sectionLabel: string;
  lineType: "service" | "expense" | "discount" | "adjustment";
  description: string;
  quantity: string;
  unit: string;
  rate: string;
  amount: string;
  reviewStatus: "pending" | "approved" | "rejected";
  reviewerNote: string;
};

function normalizeFieldDecisions(run: QuoteIngestionRunDetail): EditableFieldDecision[] {
  return (run.fieldDecisions ?? []).map((decision) => ({
    id: decision.id,
    fieldPath: decision.fieldPath,
    selectedResultId: decision.selectedResultId ?? "",
    reviewedText: decision.reviewedText ?? "",
    reviewedAmount:
      decision.reviewedAmount === null || decision.reviewedAmount === undefined
        ? ""
        : String(decision.reviewedAmount),
    reviewedDate: decision.reviewedDate ?? "",
    reviewStatus: decision.reviewStatus as EditableFieldDecision["reviewStatus"],
    reviewerNote: decision.reviewerNote ?? "",
  }));
}

function normalizeLineDecisions(run: QuoteIngestionRunDetail): EditableLineDecision[] {
  return (run.lineItemDecisions ?? []).map((decision) => ({
    id: decision.id,
    sortOrder: decision.sortOrder,
    sourceResultId: decision.sourceResultId ?? "",
    sectionLabel: decision.sectionLabel,
    lineType: decision.lineType as EditableLineDecision["lineType"],
    description: decision.description,
    quantity: String(decision.quantity),
    unit: decision.unit,
    rate: String(decision.rate),
    amount: String(decision.amount),
    reviewStatus: decision.reviewStatus as EditableLineDecision["reviewStatus"],
    reviewerNote: decision.reviewerNote ?? "",
  }));
}

function parseOptionalNumber(value: string) {
  if (!value.trim()) {
    return null;
  }
  return Number(value);
}

function fieldKind(
  fieldPath: string,
  candidates: QuoteIngestionRunDetail["fieldCandidates"] | undefined,
) {
  if (fieldPath.endsWith(".date")) {
    return "date";
  }
  if (
    fieldPath.startsWith("totals.") ||
    (candidates ?? []).some((candidate) => candidate.normalizedAmount !== null)
  ) {
    return "amount";
  }
  return "text";
}

function lineNumberInputClassName() {
  return "rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200";
}

export function PdfIngestionRunWorkspace({
  initialRun,
  projects,
  quotes,
}: {
  initialRun: QuoteIngestionRunDetail;
  projects: ProjectSummary[];
  quotes: QuoteSummary[];
}) {
  const api = getBrowserApiClient();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [selectedProjectId, setSelectedProjectId] = useState(initialRun.selectedProjectId ?? "");
  const [selectedQuoteId, setSelectedQuoteId] = useState(initialRun.selectedQuoteId ?? "");
  const [targetMode, setTargetMode] = useState(initialRun.selectedTargetMode ?? "new_quote");
  const [acknowledgedWarnings, setAcknowledgedWarnings] = useState<string[]>(
    initialRun.acknowledgedWarningCodes ?? [],
  );
  const [fieldDecisions, setFieldDecisions] = useState<EditableFieldDecision[]>(
    normalizeFieldDecisions(initialRun),
  );
  const [lineDecisions, setLineDecisions] = useState<EditableLineDecision[]>(
    normalizeLineDecisions(initialRun),
  );
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const runQuery = useQuery({
    initialData: initialRun,
    queryFn: async () => api.getQuoteIngestionRun(initialRun.id),
    queryKey: queryKeys.quoteIngestionRun(initialRun.id),
    refetchInterval: (query) =>
      query.state.data?.status === "queued" ? 5000 : false,
  });

  useEffect(() => {
    if (!runQuery.data) {
      return;
    }

    setSelectedProjectId(runQuery.data.selectedProjectId ?? "");
    setSelectedQuoteId(runQuery.data.selectedQuoteId ?? "");
    setTargetMode(runQuery.data.selectedTargetMode ?? "new_quote");
    setAcknowledgedWarnings(runQuery.data.acknowledgedWarningCodes ?? []);
    setFieldDecisions(normalizeFieldDecisions(runQuery.data));
    setLineDecisions(normalizeLineDecisions(runQuery.data));
  }, [runQuery.data]);

  const candidateByFieldPath = useMemo(() => {
    const grouped = new Map<string, QuoteIngestionRunDetail["fieldCandidates"]>();
    (runQuery.data?.fieldCandidates ?? []).forEach((candidate) => {
      grouped.set(candidate.fieldPath, [
        ...(grouped.get(candidate.fieldPath) ?? []),
        candidate,
      ]);
    });
    return grouped;
  }, [runQuery.data]);

  const lineCandidateById = useMemo(() => {
    return new Map(
      (runQuery.data?.lineItemCandidates ?? []).map((candidate) => [candidate.id, candidate]),
    );
  }, [runQuery.data]);

  const projectQuotes = useMemo(
    () => quotes.filter((quote) => quote.projectId === selectedProjectId),
    [quotes, selectedProjectId],
  );

  const saveMutation = useMutation({
    mutationFn: async () =>
      api.updateQuoteIngestionReview(initialRun.id, {
        selectedProjectId: selectedProjectId || null,
        selectedQuoteId: targetMode === "new_version" ? selectedQuoteId || null : null,
        selectedTargetMode: targetMode === "new_version" ? "new_version" : "new_quote",
        acknowledgedWarningCodes: acknowledgedWarnings,
        fieldDecisions: fieldDecisions.map((decision) => {
          const candidates = candidateByFieldPath.get(decision.fieldPath) ?? [];
          const kind = fieldKind(decision.fieldPath, candidates);

          return {
            fieldPath: decision.fieldPath,
            selectedResultId: decision.selectedResultId || null,
            reviewedText: kind === "text" ? decision.reviewedText || null : null,
            reviewedAmount:
              kind === "amount" ? parseOptionalNumber(decision.reviewedAmount) : null,
            reviewedDate: kind === "date" ? decision.reviewedDate || null : null,
            reviewStatus: decision.reviewStatus,
            reviewerNote: decision.reviewerNote || null,
          };
        }),
        lineItemDecisions: lineDecisions.map((decision) => ({
          sortOrder: decision.sortOrder,
          sourceResultId: decision.sourceResultId || null,
          sectionLabel: decision.sectionLabel,
          lineType: decision.lineType,
          description: decision.description,
          quantity: Number(decision.quantity),
          unit: decision.unit,
          rate: Number(decision.rate),
          amount: Number(decision.amount),
          reviewStatus: decision.reviewStatus,
          reviewerNote: decision.reviewerNote || null,
        })),
      }),
    onSuccess: async (run) => {
      setError(null);
      setNotice("Review state saved.");
      queryClient.setQueryData(queryKeys.quoteIngestionRun(initialRun.id), run);
      await queryClient.invalidateQueries({ queryKey: queryKeys.quoteIngestionRuns });
    },
    onError: (caughtError: unknown) => {
      setNotice(null);
      setError(
        caughtError instanceof ApiClientError || caughtError instanceof Error
          ? caughtError.message
          : "Could not save the review changes.",
      );
    },
  });

  const approveMutation = useMutation({
    mutationFn: async () => api.approveQuoteIngestionRun(initialRun.id, {}),
    onSuccess: async (response) => {
      setError(null);
      setNotice(response.approvalSummary);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.quoteIngestionRun(initialRun.id),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.quoteIngestionRuns });
      await queryClient.invalidateQueries({ queryKey: queryKeys.quotes });
    },
    onError: (caughtError: unknown) => {
      setNotice(null);
      setError(
        caughtError instanceof ApiClientError || caughtError instanceof Error
          ? caughtError.message
          : "Could not approve the reviewed extraction.",
      );
    },
  });

  const rejectMutation = useMutation({
    mutationFn: async (reason: string) =>
      api.rejectQuoteIngestionRun(initialRun.id, { reason }),
    onSuccess: async (run) => {
      setError(null);
      setNotice(`Run rejected: ${run.failureMessage ?? "No reason recorded."}`);
      queryClient.setQueryData(queryKeys.quoteIngestionRun(initialRun.id), run);
      await queryClient.invalidateQueries({ queryKey: queryKeys.quoteIngestionRuns });
    },
    onError: (caughtError: unknown) => {
      setNotice(null);
      setError(
        caughtError instanceof ApiClientError || caughtError instanceof Error
          ? caughtError.message
          : "Could not reject the run.",
      );
    },
  });

  const rerunMutation = useMutation({
    mutationFn: async () =>
      api.rerunQuoteIngestionRun(initialRun.id, {
        parserProfile: runQuery.data?.parserProfile ?? null,
      }),
    onSuccess: async (run) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.quoteIngestionRuns });
      router.push(`/imports/pdf-ingestion/${run.id}`);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError || caughtError instanceof Error
          ? caughtError.message
          : "Could not rerun the extraction.",
      );
    },
  });

  async function handleApprove() {
    setNotice(null);
    setError(null);
    await saveMutation.mutateAsync();
    await approveMutation.mutateAsync();
  }

  function handleReject() {
    const reason = window.prompt("Enter the rejection reason for this run.");
    if (!reason) {
      return;
    }
    rejectMutation.mutate(reason);
  }

  function addManualLine() {
    const nextSortOrder =
      lineDecisions.reduce((highest, decision) => Math.max(highest, decision.sortOrder), 0) + 1;

    setLineDecisions((current) => [
      ...current,
      {
        id: `manual-${nextSortOrder}`,
        sortOrder: nextSortOrder,
        sourceResultId: "",
        sectionLabel: "General",
        lineType: "service",
        description: "",
        quantity: "1",
        unit: "day",
        rate: "0",
        amount: "0",
        reviewStatus: "pending",
        reviewerNote: "",
      },
    ]);
  }

  if (runQuery.isError || !runQuery.data) {
    return (
      <ErrorState
        title="Could not load the ingestion run"
        description="The backend did not return the requested extraction run."
      />
    );
  }

  const blockingWarnings = (runQuery.data.warnings ?? []).filter((warning) => warning.blocking);
  const summaryTotal = runQuery.data.approvalPreview.totalAmount ?? 0;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 xl:grid-cols-4">
        <SummaryStat
          label="Run Status"
          value={<StatusBadge value={runQuery.data.status} />}
          hint={`Updated ${formatDateTime(runQuery.data.updatedAt)}`}
        />
        <SummaryStat
          label="Confidence"
          value={`${runQuery.data.confidenceSummary.high} / ${runQuery.data.confidenceSummary.medium} / ${runQuery.data.confidenceSummary.low}`}
          hint="High / medium / low extracted results."
          tone={runQuery.data.confidenceSummary.low > 0 ? "warning" : "default"}
        />
        <SummaryStat
          label="Proposed Target"
          value={
            runQuery.data.approvalPreview.targetMode
              ? formatStatusLabel(runQuery.data.approvalPreview.targetMode)
              : "Unassigned"
          }
          hint={runQuery.data.approvalPreview.title ?? "No reviewed title yet"}
        />
        <SummaryStat
          label="Reviewed Total"
          value={formatCurrency(summaryTotal)}
          hint={`Source PDF: ${runQuery.data.file.fileName}`}
        />
      </div>

      {notice ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-5 py-4">
          <h3 className="text-sm font-semibold text-emerald-900">Workflow update</h3>
          <p className="mt-1 text-sm text-emerald-800">{notice}</p>
        </div>
      ) : null}
      {error ? <ErrorState title="Action failed" description={error} /> : null}

      <SectionCard
        title="Run Summary"
        description="Reviewers approve or correct the extracted fields and line items here before the quote can be created."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-2 text-sm text-slate-600">
            <p>
              <span className="font-medium text-slate-900">Source file:</span>{" "}
              <a
                className="underline"
                href={runQuery.data.file.downloadUrl}
                rel="noreferrer"
                target="_blank"
              >
                {runQuery.data.file.fileName}
              </a>
            </p>
            <p>
              <span className="font-medium text-slate-900">Parser:</span>{" "}
              {runQuery.data.parserName ?? "Pending"}{" "}
              {runQuery.data.parserVersion ? `(${runQuery.data.parserVersion})` : ""}
            </p>
            <p>
              <span className="font-medium text-slate-900">Document date:</span>{" "}
              {formatDate(
                (runQuery.data.fieldDecisions ?? []).find(
                  (item) => item.fieldPath === "quote.date",
                )
                  ?.reviewedDate,
              )}
            </p>
          </div>
          {runQuery.data.approvedQuoteId && runQuery.data.selectedProjectId ? (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
              <p className="font-semibold">Approved output recorded.</p>
              <p className="mt-1">
                Quote {runQuery.data.approvedQuoteId}, version {runQuery.data.approvedQuoteVersionId}.
              </p>
              <Link
                className="mt-3 inline-block font-medium underline"
                href={`/projects/${runQuery.data.selectedProjectId}/quotes/builder`}
              >
                Open Quote Builder
              </Link>
            </div>
          ) : null}
        </div>
      </SectionCard>

      {runQuery.data.status === "queued" ? (
        <SectionCard
          title="Awaiting Parse"
          description="The source PDF has been uploaded and queued for extraction. This page will refresh while the run is queued."
        >
          <EmptyState
            title="Parser output is not ready yet"
            description="Wait for the worker to post the extraction results, or rerun the job if it stalls."
          />
        </SectionCard>
      ) : null}

      {runQuery.data.status === "failed" ? (
        <SectionCard
          title="Parse Failed"
          description="The worker could not extract a reviewable payload from the PDF."
          actions={
            <Button disabled={rerunMutation.isPending} onClick={() => rerunMutation.mutate()}>
              {rerunMutation.isPending ? "Requeueing..." : "Rerun Extraction"}
            </Button>
          }
        >
          <ErrorState
            title={runQuery.data.failureCode ?? "Parse failed"}
            description={runQuery.data.failureMessage ?? "The parser did not return a usable extraction result."}
          />
        </SectionCard>
      ) : null}

      {runQuery.data.status === "in_review" || runQuery.data.status === "approved" ? (
        <>
          <SectionCard
            title="Approval Blockers"
            description="These rules are derived from the staged review state. The run cannot be approved until all blockers are cleared."
          >
            {(runQuery.data.approvalBlockers ?? []).length ? (
              <div className="space-y-2">
                {(runQuery.data.approvalBlockers ?? []).map((blocker) => (
                  <div
                    className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900"
                    key={blocker.code}
                  >
                    <p className="font-semibold">{formatStatusLabel(blocker.code)}</p>
                    <p className="mt-1">{blocker.message}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
                No blockers remain. This run is ready for approval.
              </div>
            )}
          </SectionCard>

          <SectionCard
            title="Target Selection"
            description="Choose whether the reviewed extraction creates a new quote or a new version on an existing quote."
          >
            <div className="grid gap-4 lg:grid-cols-3">
              <SelectField
                disabled={runQuery.data.status === "approved"}
                label="Target Mode"
                onChange={(event) => setTargetMode(event.target.value)}
                value={targetMode}
              >
                <option value="new_quote">New Quote</option>
                <option value="new_version">New Version</option>
              </SelectField>
              <SelectField
                disabled={runQuery.data.status === "approved"}
                label="Project"
                onChange={(event) => setSelectedProjectId(event.target.value)}
                value={selectedProjectId}
              >
                <option value="">Select project</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </SelectField>
              <SelectField
                disabled={runQuery.data.status === "approved" || targetMode !== "new_version"}
                label="Existing Quote"
                onChange={(event) => setSelectedQuoteId(event.target.value)}
                value={selectedQuoteId}
              >
                <option value="">Select quote</option>
                {projectQuotes.map((quote) => (
                  <option key={quote.id} value={quote.id}>
                    {quote.title ?? quote.id}
                  </option>
                ))}
              </SelectField>
            </div>
          </SectionCard>

          <SectionCard
            title="Warnings"
            description="Blocking warnings must be acknowledged or corrected before approval."
          >
            {(runQuery.data.warnings ?? []).length ? (
              <div className="space-y-3">
                {(runQuery.data.warnings ?? []).map((warning) => {
                  const checked = acknowledgedWarnings.includes(warning.code);
                  return (
                    <div
                      className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3"
                      key={warning.code}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="space-y-1">
                          <p className="text-sm font-semibold text-slate-900">
                            {warning.code}
                          </p>
                          <p className="text-sm text-slate-600">{warning.message}</p>
                        </div>
                        {warning.blocking ? (
                          <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                            <input
                              checked={checked}
                              disabled={runQuery.data.status === "approved"}
                              onChange={(event) =>
                                setAcknowledgedWarnings((current) =>
                                  event.target.checked
                                    ? [...current, warning.code]
                                    : current.filter((code) => code !== warning.code),
                                )
                              }
                              type="checkbox"
                            />
                            Acknowledge
                          </label>
                        ) : (
                          <StatusBadge value={warning.severity} />
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <EmptyState
                title="No parser warnings"
                description="This run does not currently have any extraction warnings."
              />
            )}
          </SectionCard>

          <SectionCard
            title="Field Review"
            description="Each required field must be approved or corrected. You can select a parser candidate or leave the source unselected to enter a manual correction."
          >
            <div className="space-y-4">
              {fieldDecisions.map((decision) => {
                const candidates = candidateByFieldPath.get(decision.fieldPath) ?? [];
                const kind = fieldKind(decision.fieldPath, candidates);
                const selectedCandidate = candidates.find(
                  (candidate) => candidate.id === decision.selectedResultId,
                );

                return (
                  <article
                    className="rounded-lg border border-slate-200 bg-slate-50 p-4"
                    key={decision.fieldPath}
                  >
                    <div className="grid gap-4 xl:grid-cols-[0.9fr_1.6fr_0.7fr]">
                      <div className="space-y-2">
                        <p className="text-sm font-semibold text-slate-900">
                          {decision.fieldPath}
                        </p>
                        <SelectField
                          disabled={runQuery.data.status === "approved"}
                          label="Selected Source"
                          onChange={(event) =>
                            setFieldDecisions((current) =>
                              current.map((item) =>
                                item.fieldPath === decision.fieldPath
                                  ? { ...item, selectedResultId: event.target.value }
                                  : item,
                              ),
                            )
                          }
                          value={decision.selectedResultId}
                        >
                          <option value="">Manual correction</option>
                          {candidates.map((candidate) => (
                            <option key={candidate.id} value={candidate.id}>
                              {candidate.normalizedText ??
                                candidate.normalizedAmount ??
                                candidate.normalizedDate ??
                                candidate.rawValue ??
                                candidate.id}{" "}
                              ({candidate.confidenceFlag})
                            </option>
                          ))}
                        </SelectField>
                        {selectedCandidate?.sourceSnippet ? (
                          <p className="text-xs text-slate-500">
                            Source: {selectedCandidate.sourceSnippet}
                          </p>
                        ) : null}
                      </div>
                      <div className="space-y-3">
                        {kind === "text" ? (
                          <TextInput
                            disabled={runQuery.data.status === "approved"}
                            label="Reviewed Text"
                            onChange={(event) =>
                              setFieldDecisions((current) =>
                                current.map((item) =>
                                  item.fieldPath === decision.fieldPath
                                    ? { ...item, reviewedText: event.target.value }
                                    : item,
                                ),
                              )
                            }
                            value={decision.reviewedText}
                          />
                        ) : null}
                        {kind === "amount" ? (
                          <label className="grid gap-1.5">
                            <span className="text-sm font-medium text-slate-700">
                              Reviewed Amount
                            </span>
                            <input
                              className={lineNumberInputClassName()}
                              disabled={runQuery.data.status === "approved"}
                              onChange={(event) =>
                                setFieldDecisions((current) =>
                                  current.map((item) =>
                                    item.fieldPath === decision.fieldPath
                                      ? { ...item, reviewedAmount: event.target.value }
                                      : item,
                                  ),
                                )
                              }
                              step="0.01"
                              type="number"
                              value={decision.reviewedAmount}
                            />
                          </label>
                        ) : null}
                        {kind === "date" ? (
                          <TextInput
                            disabled={runQuery.data.status === "approved"}
                            label="Reviewed Date"
                            onChange={(event) =>
                              setFieldDecisions((current) =>
                                current.map((item) =>
                                  item.fieldPath === decision.fieldPath
                                    ? { ...item, reviewedDate: event.target.value }
                                    : item,
                                ),
                              )
                            }
                            type="date"
                            value={decision.reviewedDate}
                          />
                        ) : null}
                        <TextAreaField
                          disabled={runQuery.data.status === "approved"}
                          label="Reviewer Note"
                          onChange={(event) =>
                            setFieldDecisions((current) =>
                              current.map((item) =>
                                item.fieldPath === decision.fieldPath
                                  ? { ...item, reviewerNote: event.target.value }
                                  : item,
                              ),
                            )
                          }
                          value={decision.reviewerNote}
                        />
                      </div>
                      <SelectField
                        disabled={runQuery.data.status === "approved"}
                        label="Review Status"
                        onChange={(event) =>
                          setFieldDecisions((current) =>
                            current.map((item) =>
                              item.fieldPath === decision.fieldPath
                                ? {
                                    ...item,
                                    reviewStatus:
                                      event.target.value as EditableFieldDecision["reviewStatus"],
                                  }
                                : item,
                            ),
                          )
                        }
                        value={decision.reviewStatus}
                      >
                        <option value="pending">Pending</option>
                        <option value="approved">Approved</option>
                        <option value="rejected">Rejected</option>
                      </SelectField>
                    </div>
                  </article>
                );
              })}
            </div>
          </SectionCard>

          <SectionCard
            title="Line Item Review"
            description="Approve or correct each extracted line item. Additional manual rows can be added when the parser missed charge lines."
            actions={
              runQuery.data.status !== "approved" ? (
                <Button onClick={addManualLine}>Add Manual Line</Button>
              ) : null
            }
          >
            {lineDecisions.length ? (
              <div className="space-y-4">
                {lineDecisions.map((decision) => {
                  const sourceCandidate = decision.sourceResultId
                    ? lineCandidateById.get(decision.sourceResultId)
                    : null;

                  return (
                    <article
                      className="rounded-lg border border-slate-200 bg-slate-50 p-4"
                      key={`${decision.id}-${decision.sortOrder}`}
                    >
                      <div className="grid gap-3 xl:grid-cols-6">
                        <TextInput
                          disabled={runQuery.data.status === "approved"}
                          label="Section"
                          onChange={(event) =>
                            setLineDecisions((current) =>
                              current.map((item) =>
                                item.id === decision.id
                                  ? { ...item, sectionLabel: event.target.value }
                                  : item,
                              ),
                            )
                          }
                          value={decision.sectionLabel}
                        />
                        <SelectField
                          disabled={runQuery.data.status === "approved"}
                          label="Line Type"
                          onChange={(event) =>
                            setLineDecisions((current) =>
                              current.map((item) =>
                                item.id === decision.id
                                  ? {
                                      ...item,
                                      lineType:
                                        event.target.value as EditableLineDecision["lineType"],
                                    }
                                  : item,
                              ),
                            )
                          }
                          value={decision.lineType}
                        >
                          <option value="service">Service</option>
                          <option value="expense">Expense</option>
                          <option value="discount">Discount</option>
                          <option value="adjustment">Adjustment</option>
                        </SelectField>
                        <TextInput
                          disabled={runQuery.data.status === "approved"}
                          label="Description"
                          onChange={(event) =>
                            setLineDecisions((current) =>
                              current.map((item) =>
                                item.id === decision.id
                                  ? { ...item, description: event.target.value }
                                  : item,
                              ),
                            )
                          }
                          value={decision.description}
                        />
                        <TextInput
                          disabled={runQuery.data.status === "approved"}
                          label="Unit"
                          onChange={(event) =>
                            setLineDecisions((current) =>
                              current.map((item) =>
                                item.id === decision.id
                                  ? { ...item, unit: event.target.value }
                                  : item,
                              ),
                            )
                          }
                          value={decision.unit}
                        />
                        <label className="grid gap-1.5">
                          <span className="text-sm font-medium text-slate-700">Quantity</span>
                          <input
                            className={lineNumberInputClassName()}
                            disabled={runQuery.data.status === "approved"}
                            onChange={(event) =>
                              setLineDecisions((current) =>
                                current.map((item) =>
                                  item.id === decision.id
                                    ? { ...item, quantity: event.target.value }
                                    : item,
                                ),
                              )
                            }
                            step="0.01"
                            type="number"
                            value={decision.quantity}
                          />
                        </label>
                        <label className="grid gap-1.5">
                          <span className="text-sm font-medium text-slate-700">Rate</span>
                          <input
                            className={lineNumberInputClassName()}
                            disabled={runQuery.data.status === "approved"}
                            onChange={(event) =>
                              setLineDecisions((current) =>
                                current.map((item) =>
                                  item.id === decision.id
                                    ? { ...item, rate: event.target.value }
                                    : item,
                                ),
                              )
                            }
                            step="0.01"
                            type="number"
                            value={decision.rate}
                          />
                        </label>
                      </div>
                      <div className="mt-3 grid gap-3 xl:grid-cols-[0.6fr_0.6fr_1.5fr]">
                        <label className="grid gap-1.5">
                          <span className="text-sm font-medium text-slate-700">Amount</span>
                          <input
                            className={lineNumberInputClassName()}
                            disabled={runQuery.data.status === "approved"}
                            onChange={(event) =>
                              setLineDecisions((current) =>
                                current.map((item) =>
                                  item.id === decision.id
                                    ? { ...item, amount: event.target.value }
                                    : item,
                                ),
                              )
                            }
                            step="0.01"
                            type="number"
                            value={decision.amount}
                          />
                        </label>
                        <SelectField
                          disabled={runQuery.data.status === "approved"}
                          label="Review Status"
                          onChange={(event) =>
                            setLineDecisions((current) =>
                              current.map((item) =>
                                item.id === decision.id
                                  ? {
                                      ...item,
                                      reviewStatus:
                                        event.target.value as EditableLineDecision["reviewStatus"],
                                    }
                                  : item,
                              ),
                            )
                          }
                          value={decision.reviewStatus}
                        >
                          <option value="pending">Pending</option>
                          <option value="approved">Approved</option>
                          <option value="rejected">Rejected</option>
                        </SelectField>
                        <TextAreaField
                          disabled={runQuery.data.status === "approved"}
                          label="Reviewer Note"
                          onChange={(event) =>
                            setLineDecisions((current) =>
                              current.map((item) =>
                                item.id === decision.id
                                  ? { ...item, reviewerNote: event.target.value }
                                  : item,
                              ),
                            )
                          }
                          value={decision.reviewerNote}
                        />
                      </div>
                      {sourceCandidate ? (
                        <p className="mt-3 text-xs text-slate-500">
                          Extracted source: {sourceCandidate.sourceSnippet} ({sourceCandidate.confidenceFlag})
                        </p>
                      ) : (
                        <p className="mt-3 text-xs text-slate-500">
                          Manual review row.
                        </p>
                      )}
                    </article>
                  );
                })}
              </div>
            ) : (
              <EmptyState
                title="No staged line items"
                description="Add a manual line item if the parser did not extract any rows."
              />
            )}
          </SectionCard>

          {runQuery.data.status === "in_review" ? (
            <InlineActionBar sticky>
              <Button
                disabled={saveMutation.isPending || approveMutation.isPending}
                onClick={() => saveMutation.mutate()}
              >
                {saveMutation.isPending ? "Saving..." : "Save Review"}
              </Button>
              <Button
                disabled={
                  saveMutation.isPending ||
                  approveMutation.isPending ||
                  runQuery.data.status !== "in_review"
                }
                onClick={() => void handleApprove()}
                variant="primary"
              >
                {approveMutation.isPending ? "Approving..." : "Approve Into Quote Version"}
              </Button>
              <Button
                disabled={rejectMutation.isPending}
                onClick={handleReject}
                variant="danger"
              >
                {rejectMutation.isPending ? "Rejecting..." : "Reject Run"}
              </Button>
              <Button disabled={rerunMutation.isPending} onClick={() => rerunMutation.mutate()}>
                {rerunMutation.isPending ? "Requeueing..." : "Rerun Extraction"}
              </Button>
              <Link className="ml-auto text-sm font-medium text-slate-900 underline" href="/imports/pdf-ingestion">
                Back To Run List
              </Link>
            </InlineActionBar>
          ) : null}
        </>
      ) : null}

      {blockingWarnings.length && runQuery.data.status === "approved" ? (
        <SectionCard
          title="Acknowledged Blocking Warnings"
          description="These warnings were explicitly acknowledged during review before approval."
        >
          <ul className="space-y-2 text-sm text-slate-600">
            {blockingWarnings.map((warning) => (
              <li key={warning.code}>
                <span className="font-medium text-slate-900">{warning.code}</span>: {warning.message}
              </li>
            ))}
          </ul>
        </SectionCard>
      ) : null}
    </div>
  );
}
