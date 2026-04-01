"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import type {
  AuditEventSummary,
  ForecastDetailRead,
  ForecastLineRead,
  ForecastPolicySummary,
  ForecastVersionRead,
  ProjectScheduleRangeRead
} from "@quotes4/contracts";
import { ApiClientError } from "@quotes4/contracts";

import { getBrowserApiClient } from "@/lib/api/browser-client";
import { formatCurrency, formatDate, formatDateTime, formatPercent, formatStatusLabel } from "@/lib/format";
import { queryKeys } from "@/lib/query/keys";

import { InlineActionBar } from "@/components/forms/inline-action-bar";
import { SegmentedControl } from "@/components/forms/segmented-control";
import { SelectField } from "@/components/forms/select-field";
import { TextAreaField } from "@/components/forms/text-area-field";
import { TextInput } from "@/components/forms/text-input";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SummaryStat } from "@/components/ui/summary-stat";
import { Button } from "@/components/ui/button";

type AllocationMethod = "manual" | "schedule";

type AllocationDraft = {
  id: string;
  month: string;
  amount: string;
};

type LineDraft = {
  allocationMethod: AllocationMethod;
  scheduleRangeId: string;
  reason: string;
  allocations: AllocationDraft[];
};

type LineDraftState = Record<string, LineDraft>;

function buildAllocationId(lineId: string, index: number): string {
  return `${lineId}:${index}`;
}

function buildLineDraft(line: ForecastLineRead): LineDraft {
  return {
    allocationMethod:
      line.allocationMethod === "manual" ? "manual" : "schedule",
    scheduleRangeId: line.scheduleRangeId ?? "",
    reason: "",
    allocations: line.allocations.map((allocation, index) => ({
      id: buildAllocationId(line.id, index),
      month: allocation.month,
      amount: String(allocation.amount)
    }))
  };
}

function toLineDraftState(version: ForecastVersionRead | null): LineDraftState {
  if (!version) {
    return {};
  }

  return Object.fromEntries(
    version.lines.map((line) => [line.id, buildLineDraft(line)])
  );
}

function nextMonth(value?: string): string {
  if (!value) {
    const today = new Date();
    return `${today.getUTCFullYear()}-${String(today.getUTCMonth() + 1).padStart(2, "0")}`;
  }

  const [yearText, monthText] = value.split("-");
  const year = Number(yearText);
  const month = Number(monthText);

  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    return value;
  }

  const next = new Date(Date.UTC(year, month, 1));
  return `${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, "0")}`;
}

function formatScheduleRangeLabel(range: ProjectScheduleRangeRead): string {
  const disciplineLabel = range.disciplineName ?? "Shared";
  const percentLabel =
    range.allocationPercent !== null && range.allocationPercent !== undefined
      ? ` · ${range.allocationPercent.toFixed(2)}%`
      : "";

  return `${range.label} · ${disciplineLabel} · ${formatDate(range.startDate)} to ${formatDate(
    range.endDate
  )}${percentLabel}`;
}

function getScheduleRangeOptions(
  line: ForecastLineRead,
  projectScheduleRanges: ProjectScheduleRangeRead[]
): ProjectScheduleRangeRead[] {
  return projectScheduleRanges.filter((range) => {
    if (line.scheduleRangeId && range.id === line.scheduleRangeId) {
      return true;
    }

    return range.disciplineId === line.disciplineId || range.disciplineId == null;
  });
}

function describeAuditEvent(event: AuditEventSummary): string {
  if (event.summary) {
    return event.summary;
  }

  return formatStatusLabel(event.action);
}

export function ForecastEditor({
  projectId,
  initialForecast,
  initialPolicy,
  projectScheduleRanges
}: {
  projectId: string;
  initialForecast: ForecastDetailRead;
  initialPolicy: ForecastPolicySummary;
  projectScheduleRanges: ProjectScheduleRangeRead[];
}) {
  const api = getBrowserApiClient();
  const queryClient = useQueryClient();
  const [selectedVersionId, setSelectedVersionId] = useState(
    initialForecast.currentVersionId ?? initialForecast.versions[0]?.id ?? ""
  );
  const [title, setTitle] = useState("");
  const [notesText, setNotesText] = useState("");
  const [probabilityPercent, setProbabilityPercent] = useState("100");
  const [revisionReason, setRevisionReason] = useState("");
  const [lineDrafts, setLineDrafts] = useState<LineDraftState>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const forecastQuery = useQuery({
    initialData: initialForecast,
    queryFn: async () => api.getProjectForecast(projectId),
    queryKey: queryKeys.projectForecast(projectId)
  });

  const policyQuery = useQuery({
    initialData: initialPolicy,
    queryFn: async () => api.getForecastPolicy(),
    queryKey: queryKeys.forecastPolicy
  });

  const auditQuery = useQuery({
    queryFn: async () => api.listAuditEvents({ limit: 12, projectId }),
    queryKey: queryKeys.auditEvents(projectId),
    retry: false
  });

  const selectedVersionSummary = useMemo(
    () => forecastQuery.data.versions.find((version) => version.id === selectedVersionId) ?? null,
    [forecastQuery.data.versions, selectedVersionId]
  );

  const selectedVersionQuery = useQuery({
    enabled: Boolean(selectedVersionId),
    initialData:
      forecastQuery.data.currentVersion?.id === selectedVersionId
        ? forecastQuery.data.currentVersion
        : undefined,
    queryFn: async () => api.getForecastVersion(selectedVersionId),
    queryKey: queryKeys.forecastVersion(selectedVersionId || "none")
  });

  useEffect(() => {
    const version = selectedVersionQuery.data;
    if (!version) {
      return;
    }

    setTitle(version.title ?? "");
    setNotesText(version.notesText ?? "");
    setProbabilityPercent(String(version.probabilityPercent));
    setRevisionReason(version.revisionReason ?? "");
    setLineDrafts(toLineDraftState(version));
  }, [selectedVersionQuery.data]);

  const clearFeedback = () => {
    setError(null);
    setNotice(null);
  };

  const invalidateForecastData = async (versionId?: string) => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.projectForecast(projectId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.auditEvents(projectId) }),
      versionId
        ? queryClient.invalidateQueries({ queryKey: queryKeys.forecastVersion(versionId) })
        : Promise.resolve()
    ]);
  };

  const createDraftMutation = useMutation({
    mutationFn: async () =>
      api.createForecastVersion(projectId, {
        baseVersionId: selectedVersionId || null,
        title: title || null,
        notesText: notesText || null,
        probabilityPercent: Number(probabilityPercent),
        revisionReason: revisionReason || null
      }),
    onMutate: clearFeedback,
    onSuccess: async (version) => {
      setSelectedVersionId(version.id);
      setNotice(`Created draft forecast v${version.versionNumber}.`);
      await invalidateForecastData(version.id);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not create the forecast draft."
      );
    }
  });

  const updateVersionMutation = useMutation({
    mutationFn: async () => {
      if (!selectedVersionQuery.data) {
        throw new Error("Forecast version missing.");
      }

      return api.updateForecastVersion(selectedVersionQuery.data.id, {
        expectedUpdatedAt: selectedVersionQuery.data.updatedAt,
        title: title || null,
        notesText: notesText || null,
        probabilityPercent: Number(probabilityPercent),
        revisionReason: revisionReason || null
      });
    },
    onMutate: clearFeedback,
    onSuccess: async (version) => {
      setNotice(`Saved metadata for draft v${version.versionNumber}.`);
      await invalidateForecastData(version.id);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not save the forecast version."
      );
    }
  });

  const lineMutation = useMutation({
    mutationFn: async (lineId: string) => {
      const version = selectedVersionQuery.data;
      const line = version?.lines.find((item) => item.id === lineId);
      const draft = lineDrafts[lineId];

      if (!version || !line || !draft) {
        throw new Error("Forecast line missing.");
      }

      return api.replaceForecastLineAllocations(lineId, {
        expectedUpdatedAt: version.updatedAt,
        allocationMethod: draft.allocationMethod,
        allocations:
          draft.allocationMethod === "manual"
            ? draft.allocations
                .filter((allocation) => allocation.month || allocation.amount)
                .map((allocation) => ({
                  month: allocation.month,
                  amount: Number(allocation.amount)
                }))
            : [],
        reason: draft.reason || null,
        scheduleRangeId: draft.scheduleRangeId || null
      });
    },
    onMutate: clearFeedback,
    onSuccess: async (version) => {
      setNotice(`Saved line allocations for forecast v${version.versionNumber}.`);
      await invalidateForecastData(version.id);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not save line allocations."
      );
    }
  });

  const submitMutation = useMutation({
    mutationFn: async () => {
      if (!selectedVersionId) {
        throw new Error("Forecast version missing.");
      }

      return api.submitForecastVersion(selectedVersionId);
    },
    onMutate: clearFeedback,
    onSuccess: async (version) => {
      setNotice(`Submitted forecast v${version.versionNumber}.`);
      await invalidateForecastData(version.id);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not submit the forecast version."
      );
    }
  });

  const lockMutation = useMutation({
    mutationFn: async () => {
      if (!selectedVersionId) {
        throw new Error("Forecast version missing.");
      }

      return api.lockForecastVersion(selectedVersionId);
    },
    onMutate: clearFeedback,
    onSuccess: async (version) => {
      setNotice(`Locked forecast v${version.versionNumber}.`);
      await invalidateForecastData(version.id);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not lock the forecast version."
      );
    }
  });

  const recalcMutation = useMutation({
    mutationFn: async () => api.recalculateForecast(projectId),
    onMutate: clearFeedback,
    onSuccess: async (response) => {
      if (response.forecastVersionId) {
        setSelectedVersionId(response.forecastVersionId);
      }
      setNotice(response.message);
      await invalidateForecastData(response.forecastVersionId ?? undefined);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not recalculate the forecast."
      );
    }
  });

  const version = selectedVersionQuery.data;
  const isDraftVersion = version?.status === "draft";
  const canSubmitVersion = version?.status === "draft";
  const canLockVersion = version?.status === "draft" || version?.status === "submitted";
  const auditUnavailable =
    auditQuery.error instanceof ApiClientError && auditQuery.error.status === 403;

  return (
    <div className="space-y-6">
      {error ? <ErrorState description={error} title="Forecast action failed" /> : null}
      {notice ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm text-emerald-900">
          {notice}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-5">
        <SummaryStat label="Current status" value={version ? formatStatusLabel(version.status) : "Unknown"} />
        <SummaryStat label="Total" value={version ? formatCurrency(version.totalAmount) : "Not set"} />
        <SummaryStat
          label="Weighted total"
          value={version ? formatCurrency(version.weightedTotalAmount) : "Not set"}
        />
        <SummaryStat label="Probability" value={version ? formatPercent(version.probabilityPercent) : "Not set"} />
        <SummaryStat
          label="Quote basis"
          value={
            version ? (version.isSourceQuoteCurrent ? "Current quote" : "Needs rebase") : "Not set"
          }
        />
      </div>

      <SectionCard
        title="Version Control"
        description="Select the working forecast version and run core lifecycle actions."
      >
        <div className="grid gap-4 md:grid-cols-[minmax(0,320px)_1fr]">
          <SelectField
            label="Version"
            onChange={(event) => setSelectedVersionId(event.target.value)}
            value={selectedVersionId}
          >
            {forecastQuery.data.versions.map((forecastVersion) => (
              <option key={forecastVersion.id} value={forecastVersion.id}>
                V{forecastVersion.versionNumber} · {formatStatusLabel(forecastVersion.status)}
              </option>
            ))}
          </SelectField>
          <div className="flex flex-wrap items-center gap-2 self-end">
            {selectedVersionSummary ? <StatusBadge value={selectedVersionSummary.status} /> : null}
            <Button onClick={() => createDraftMutation.mutate()} type="button" variant="primary">
              {createDraftMutation.isPending ? "Creating..." : "Create draft"}
            </Button>
            <Button
              disabled={!selectedVersionId || !canSubmitVersion || submitMutation.isPending}
              onClick={() => submitMutation.mutate()}
              type="button"
            >
              Submit
            </Button>
            <Button
              disabled={!selectedVersionId || !canLockVersion || lockMutation.isPending}
              onClick={() => lockMutation.mutate()}
              type="button"
            >
              Lock
            </Button>
            <Button onClick={() => recalcMutation.mutate()} type="button" variant="ghost">
              {recalcMutation.isPending ? "Recalculating..." : "Recalculate"}
            </Button>
          </div>
        </div>
        <p className="mt-4 text-sm text-slate-600">
          Supported methods: {policyQuery.data.supportedMethods.join(", ")}. Outcomes:{" "}
          {policyQuery.data.supportedOutcomes.join(", ")}. Triggers:{" "}
          {policyQuery.data.recalcTriggers.join(", ")}.
        </p>
      </SectionCard>

      {version ? (
        <>
          {version.issues.length > 0 ? (
            <SectionCard
              title="Validation and Traceability"
              description="The current version has issues that should be resolved before submission or lock."
            >
              <div className="space-y-2">
                {version.issues.map((issue) => (
                  <div
                    className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
                    key={issue}
                  >
                    {issue}
                  </div>
                ))}
              </div>
            </SectionCard>
          ) : null}

          {!isDraftVersion ? (
            <SectionCard
              title="Read-Only Version"
              description="Submitted and locked versions stay immutable. Create a draft to make changes."
            >
              <p className="text-sm text-slate-600">
                This version is currently {formatStatusLabel(version.status).toLowerCase()}.{" "}
                Metadata and line allocations are shown for review only.
              </p>
            </SectionCard>
          ) : null}

          <SectionCard
            title="Version Metadata"
            description="Edit version metadata, probability, and revision rationale."
          >
            <div className="grid gap-4 md:grid-cols-2">
              <TextInput
                disabled={!isDraftVersion}
                label="Title"
                onChange={(event) => setTitle(event.target.value)}
                value={title}
              />
              <TextInput
                disabled={
                  !isDraftVersion ||
                  version.outcomeTypeSnapshot === "awarded" ||
                  version.outcomeTypeSnapshot === "lost"
                }
                label="Probability percent"
                onChange={(event) => setProbabilityPercent(event.target.value)}
                step="0.01"
                type="number"
                value={probabilityPercent}
              />
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <TextAreaField
                disabled={!isDraftVersion}
                label="Notes"
                onChange={(event) => setNotesText(event.target.value)}
                value={notesText}
              />
              <TextAreaField
                disabled={!isDraftVersion}
                label="Revision reason"
                onChange={(event) => setRevisionReason(event.target.value)}
                value={revisionReason}
              />
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                <p className="font-medium text-slate-900">Outcome bucket</p>
                <p className="mt-1">{formatStatusLabel(version.outcomeTypeSnapshot)}</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                <p className="font-medium text-slate-900">Source quote version</p>
                <p className="mt-1">{version.sourceQuoteVersionId ?? "Not linked"}</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                <p className="font-medium text-slate-900">Quote source status</p>
                <p className="mt-1">{version.isSourceQuoteCurrent ? "Current" : "Stale"}</p>
              </div>
            </div>
            <div className="mt-4">
              <InlineActionBar>
                <Button
                  disabled={!isDraftVersion || updateVersionMutation.isPending}
                  onClick={() => updateVersionMutation.mutate()}
                  type="button"
                  variant="primary"
                >
                  {updateVersionMutation.isPending ? "Saving..." : "Save metadata"}
                </Button>
              </InlineActionBar>
            </div>
          </SectionCard>

          <SectionCard
            title="Monthly Rollup"
            description="Review the current project-level month spread before or after allocation edits."
          >
            {version.projectMonthlyRollups.length === 0 ? (
              <p className="text-sm text-slate-600">No monthly rollup is available yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50 text-left text-slate-600">
                    <tr>
                      <th className="px-3 py-2 font-medium">Month</th>
                      <th className="px-3 py-2 font-medium">Amount</th>
                      <th className="px-3 py-2 font-medium">Weighted amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {version.projectMonthlyRollups.map((rollup) => (
                      <tr key={rollup.month}>
                        <td className="px-3 py-2 text-slate-900">{rollup.month}</td>
                        <td className="px-3 py-2 text-slate-700">{formatCurrency(rollup.amount)}</td>
                        <td className="px-3 py-2 text-slate-700">
                          {formatCurrency(rollup.weightedAmount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>

          <SectionCard
            title="Line Allocations"
            description="Switch between schedule-driven and manual allocation per line, then save with a rationale."
          >
            <div className="space-y-4">
              {version.lines.map((line) => {
                const draft = lineDrafts[line.id] ?? buildLineDraft(line);
                const scheduleOptions = getScheduleRangeOptions(line, projectScheduleRanges);

                return (
                  <div className="space-y-4 rounded-lg border border-slate-200 p-4" key={line.id}>
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div className="space-y-1">
                        <p className="font-medium text-slate-900">{line.label}</p>
                        <p className="text-sm text-slate-600">
                          {formatCurrency(line.totalAmount, line.currencyCode)} total ·{" "}
                          {formatCurrency(line.weightedTotalAmount, line.currencyCode)} weighted
                        </p>
                        <p className="text-xs text-slate-500">Source line: {line.sourceLineId}</p>
                      </div>
                      <SegmentedControl<AllocationMethod>
                        disabled={!isDraftVersion}
                        onChange={(value) =>
                          setLineDrafts((current) => {
                            const currentDraft = current[line.id] ?? buildLineDraft(line);

                            return {
                              ...current,
                              [line.id]: {
                                ...currentDraft,
                                allocationMethod: value,
                                allocations:
                                  value === "manual" && currentDraft.allocations.length === 0
                                    ? buildLineDraft(line).allocations
                                    : currentDraft.allocations
                              }
                            };
                          })
                        }
                        options={[
                          { label: "Schedule", value: "schedule" },
                          { label: "Manual", value: "manual" }
                        ]}
                        value={draft.allocationMethod}
                      />
                    </div>

                    {line.issues.length > 0 ? (
                      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                        {line.issues.join(", ")}
                      </div>
                    ) : null}

                    {line.notes ? (
                      <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                        {line.notes}
                      </div>
                    ) : null}

                    {draft.allocationMethod === "schedule" ? (
                      <>
                        <SelectField
                          disabled={!isDraftVersion}
                          label="Schedule range"
                          onChange={(event) =>
                            setLineDrafts((current) => ({
                              ...current,
                              [line.id]: {
                                ...(current[line.id] ?? buildLineDraft(line)),
                                scheduleRangeId: event.target.value
                              }
                            }))
                          }
                          value={draft.scheduleRangeId}
                        >
                          <option value="">Automatic by discipline</option>
                          {scheduleOptions.map((range) => (
                            <option key={range.id} value={range.id}>
                              {formatScheduleRangeLabel(range)}
                            </option>
                          ))}
                        </SelectField>
                        <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                          Schedule-driven lines are recalculated from project schedule ranges. Save the line after selecting
                          a specific range or use the global recalculation action after schedule changes.
                        </div>
                        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-4">
                          {line.allocations.map((allocation) => (
                            <div
                              className="rounded-md border border-slate-200 bg-white px-4 py-3"
                              key={`${line.id}:${allocation.month}`}
                            >
                              <p className="text-sm font-medium text-slate-900">{allocation.month}</p>
                              <p className="mt-1 text-sm text-slate-700">
                                {formatCurrency(allocation.amount, line.currencyCode)}
                              </p>
                              <p className="text-xs text-slate-500">
                                Weighted {formatCurrency(allocation.weightedAmount, line.currencyCode)}
                              </p>
                            </div>
                          ))}
                        </div>
                      </>
                    ) : (
                      <div className="space-y-3">
                        {draft.allocations.map((allocation) => (
                          <div className="grid gap-3 md:grid-cols-[180px_minmax(0,1fr)_auto]" key={allocation.id}>
                            <TextInput
                              disabled={!isDraftVersion}
                              label="Month"
                              onChange={(event) =>
                                setLineDrafts((current) => ({
                                  ...current,
                                  [line.id]: {
                                    ...(current[line.id] ?? buildLineDraft(line)),
                                    allocations: (current[line.id]?.allocations ?? buildLineDraft(line).allocations).map(
                                      (item) =>
                                        item.id === allocation.id
                                          ? { ...item, month: event.target.value }
                                          : item
                                    )
                                  }
                                }))
                              }
                              type="month"
                              value={allocation.month}
                            />
                            <TextInput
                              disabled={!isDraftVersion}
                              label="Amount"
                              onChange={(event) =>
                                setLineDrafts((current) => ({
                                  ...current,
                                  [line.id]: {
                                    ...(current[line.id] ?? buildLineDraft(line)),
                                    allocations: (current[line.id]?.allocations ?? buildLineDraft(line).allocations).map(
                                      (item) =>
                                        item.id === allocation.id
                                          ? { ...item, amount: event.target.value }
                                          : item
                                    )
                                  }
                                }))
                              }
                              step="0.01"
                              type="number"
                              value={allocation.amount}
                            />
                            <div className="self-end">
                              <Button
                                disabled={!isDraftVersion}
                                onClick={() =>
                                  setLineDrafts((current) => ({
                                    ...current,
                                    [line.id]: {
                                      ...(current[line.id] ?? buildLineDraft(line)),
                                      allocations: (
                                        current[line.id]?.allocations ?? buildLineDraft(line).allocations
                                      ).filter((item) => item.id !== allocation.id)
                                    }
                                  }))
                                }
                                type="button"
                                variant="ghost"
                              >
                                Remove
                              </Button>
                            </div>
                          </div>
                        ))}
                        <Button
                          disabled={!isDraftVersion}
                          onClick={() =>
                            setLineDrafts((current) => {
                              const currentDraft = current[line.id] ?? buildLineDraft(line);
                              const lastMonth = currentDraft.allocations[currentDraft.allocations.length - 1]?.month;

                              return {
                                ...current,
                                [line.id]: {
                                  ...currentDraft,
                                  allocations: [
                                    ...currentDraft.allocations,
                                    {
                                      id: buildAllocationId(line.id, currentDraft.allocations.length),
                                      month: nextMonth(lastMonth),
                                      amount: "0"
                                    }
                                  ]
                                }
                              };
                            })
                          }
                          type="button"
                          variant="ghost"
                        >
                          Add month
                        </Button>
                      </div>
                    )}

                    <TextAreaField
                      disabled={!isDraftVersion}
                      label="Edit rationale"
                      onChange={(event) =>
                        setLineDrafts((current) => ({
                          ...current,
                          [line.id]: {
                            ...(current[line.id] ?? buildLineDraft(line)),
                            reason: event.target.value
                          }
                        }))
                      }
                      value={draft.reason}
                    />

                    <InlineActionBar>
                      <Button
                        disabled={!isDraftVersion || lineMutation.isPending}
                        onClick={() => lineMutation.mutate(line.id)}
                        type="button"
                        variant="primary"
                      >
                        {lineMutation.isPending ? "Saving line..." : "Save line"}
                      </Button>
                    </InlineActionBar>
                  </div>
                );
              })}
            </div>
          </SectionCard>

          {!auditUnavailable ? (
            <SectionCard
              title="Recent Audit Trail"
              description="Recent audit events tied to this project. Forecast entries are shown alongside related project events."
            >
              {auditQuery.isLoading ? (
                <p className="text-sm text-slate-600">Loading audit trail...</p>
              ) : auditQuery.error ? (
                <ErrorState
                  description={
                    auditQuery.error instanceof ApiClientError
                      ? auditQuery.error.message
                      : "Could not load audit history."
                  }
                  title="Audit trail unavailable"
                />
              ) : auditQuery.data?.items.length ? (
                <div className="space-y-3">
                  {auditQuery.data.items.map((event) => (
                    <div className="rounded-lg border border-slate-200 px-4 py-3" key={event.id}>
                      <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                        <p className="text-sm font-medium text-slate-900">{describeAuditEvent(event)}</p>
                        <p className="text-xs text-slate-500">{formatDateTime(event.createdAt)}</p>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">
                        {event.action} · {event.actorEmail ?? "System"}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-600">No audit events are available for this project yet.</p>
              )}
            </SectionCard>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
