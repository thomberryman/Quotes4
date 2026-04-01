"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import type {
  ProjectComparablesResponse,
  ProjectPredictiveGuidanceResponse,
  ProjectRecommendationsResponse
} from "@quotes4/contracts";
import { ApiClientError } from "@quotes4/contracts";

import { ProjectPredictiveGuidancePanel } from "@/components/features/projects/project-predictive-guidance-panel";
import { getBrowserApiClient } from "@/lib/api/browser-client";
import { formatCurrency, formatDate, formatPercent } from "@/lib/format";
import { queryKeys } from "@/lib/query/keys";

import { CheckboxField } from "@/components/forms/checkbox-field";
import { InlineActionBar } from "@/components/forms/inline-action-bar";
import { SelectField } from "@/components/forms/select-field";
import { TextAreaField } from "@/components/forms/text-area-field";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { SummaryStat } from "@/components/ui/summary-stat";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { DisciplineRangeTable } from "@/features/dashboard/dashboard-charts";

function deriveSelection(response: ProjectComparablesResponse) {
  const pinnedProjectIds: string[] = [];
  const excludedProjectIds: string[] = [];

  response.items.forEach((item) => {
    if (item.selectionState === "pinned") {
      pinnedProjectIds.push(item.projectId);
    }
    if (item.selectionState === "excluded") {
      excludedProjectIds.push(item.projectId);
    }
  });

  return { pinnedProjectIds, excludedProjectIds };
}

export function ComparablesWorkspace({
  projectId,
  projectDisciplines,
  initialComparables,
  initialPredictiveGuidance,
  initialRecommendations
}: {
  projectId: string;
  projectDisciplines: Array<{
    code: string;
    name: string;
  }>;
  initialComparables: ProjectComparablesResponse;
  initialPredictiveGuidance: ProjectPredictiveGuidanceResponse;
  initialRecommendations: ProjectRecommendationsResponse;
}) {
  const api = getBrowserApiClient();
  const queryClient = useQueryClient();
  const [selectedDisciplineId, setSelectedDisciplineId] = useState<string>("all");
  const [includePinned, setIncludePinned] = useState(true);
  const [note, setNote] = useState("");
  const [pinnedProjectIds, setPinnedProjectIds] = useState<string[]>([]);
  const [excludedProjectIds, setExcludedProjectIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const disciplineFilter =
    selectedDisciplineId === "all" ? undefined : selectedDisciplineId;
  const comparablesQueryOptions = {
    includePinned,
    limit: 25,
    ...(disciplineFilter ? { disciplineId: disciplineFilter } : {})
  };
  const recommendationQueryOptions = {
    limit: 25,
    ...(disciplineFilter ? { disciplineId: disciplineFilter } : {})
  };

  const selectionSourceQuery = useQuery({
    initialData: initialComparables,
    queryFn: async () =>
      api.getProjectComparables(projectId, { includePinned: true, limit: 25 }),
    queryKey: queryKeys.projectComparables(projectId, {
      includePinned: true
    })
  });

  const comparablesQuery = useQuery({
    initialData:
      disciplineFilter === undefined && includePinned ? initialComparables : undefined,
    placeholderData: (previousData) => previousData,
    queryFn: async () => api.getProjectComparables(projectId, comparablesQueryOptions),
    queryKey: queryKeys.projectComparables(projectId, {
      includePinned,
      ...(disciplineFilter ? { disciplineId: disciplineFilter } : {})
    })
  });

  const recommendationsQuery = useQuery({
    initialData: disciplineFilter === undefined ? initialRecommendations : undefined,
    placeholderData: (previousData) => previousData,
    queryFn: async () =>
      api.getProjectRecommendations(projectId, recommendationQueryOptions),
    queryKey: queryKeys.projectRecommendations(projectId, {
      ...(disciplineFilter ? { disciplineId: disciplineFilter } : {})
    })
  });
  const predictiveGuidanceQuery = useQuery({
    initialData:
      disciplineFilter === undefined ? initialPredictiveGuidance : undefined,
    placeholderData: (previousData) => previousData,
    queryFn: async () =>
      api.getProjectPredictiveGuidance(projectId, recommendationQueryOptions),
    queryKey: queryKeys.projectPredictiveGuidance(projectId, {
      ...(disciplineFilter ? { disciplineId: disciplineFilter } : {})
    })
  });

  const selectionSourceData = selectionSourceQuery.data ?? initialComparables;
  const comparablesData = comparablesQuery.data ?? initialComparables;
  const predictiveGuidanceData =
    predictiveGuidanceQuery.data ?? initialPredictiveGuidance;
  const recommendationsData = recommendationsQuery.data ?? initialRecommendations;

  useEffect(() => {
    const selection = deriveSelection(selectionSourceData);
    setPinnedProjectIds(selection.pinnedProjectIds);
    setExcludedProjectIds(selection.excludedProjectIds);
  }, [selectionSourceData]);

  const selectionMutation = useMutation({
    mutationFn: async () =>
      api.updateProjectComparableSelection(projectId, {
        pinnedProjectIds,
        excludedProjectIds,
        note: note || null
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["project-comparables", projectId] });
      await queryClient.invalidateQueries({
        queryKey: ["project-recommendations", projectId]
      });
      await queryClient.invalidateQueries({
        queryKey: ["project-predictive-guidance", projectId]
      });
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not update comparable selection."
      );
    }
  });

  const overallRange = recommendationsData.overallQuoteRange;
  const actualRange = recommendationsData.overallActualInformedRange;

  return (
    <div className="space-y-6">
      {error ? <ErrorState description={error} title="Comparable update failed" /> : null}
      <SectionCard
        title="Review Filters"
        description="Narrow the visible comparable set without changing which pinned or excluded projects are stored."
      >
        <div className="grid gap-4 lg:grid-cols-[minmax(0,260px)_minmax(0,220px)_1fr]">
          <SelectField
            label="Discipline focus"
            onChange={(event) => setSelectedDisciplineId(event.target.value)}
            value={selectedDisciplineId}
          >
            <option value="all">All disciplines</option>
            {projectDisciplines.map((discipline) => (
              <option key={discipline.code} value={discipline.code}>
                {discipline.name}
              </option>
            ))}
          </SelectField>
          <div className="flex items-end">
            <CheckboxField
              checked={includePinned}
              label="Show pinned projects"
              onChange={(event) => setIncludePinned(event.target.checked)}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <SummaryStat
              label="Visible comparables"
              value={comparablesData.items.length}
            />
            <SummaryStat
              label="Eligible for guidance"
              value={
                comparablesData.items.filter((item) => item.isEligibleForRecommendations)
                  .length
              }
            />
            <SummaryStat
              label="Manual overrides"
              value={pinnedProjectIds.length + excludedProjectIds.length}
            />
          </div>
        </div>
      </SectionCard>
      <div className="grid gap-4 md:grid-cols-3">
        <SummaryStat
          label="Quote range"
          value={
            overallRange
              ? `${formatCurrency(overallRange.low, overallRange.currencyCode)} to ${formatCurrency(overallRange.high, overallRange.currencyCode)}`
              : "Not available"
          }
        />
        <SummaryStat
          label="Actual-informed median"
          value={
            actualRange
              ? formatCurrency(actualRange.median, actualRange.currencyCode)
              : "Not available"
          }
        />
        <SummaryStat
          label="Projects used"
          value={recommendationsData.comparablesUsed.length}
        />
      </div>

      <SectionCard
        title="Quote Guidance"
        description="Use the comparable quote range for first-pass guidance, then review actual-informed uplift and discipline medians before finalizing assumptions."
      >
        <div className="space-y-6">
          <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
            <div className="grid gap-4 md:grid-cols-3">
              <SummaryStat
                label="Quote low / median / high"
                value={
                  overallRange
                    ? formatCurrency(overallRange.median, overallRange.currencyCode)
                    : "Not available"
                }
                hint={
                  overallRange
                    ? `${formatCurrency(overallRange.low, overallRange.currencyCode)} to ${formatCurrency(overallRange.high, overallRange.currencyCode)}`
                    : "Need at least three eligible comparables"
                }
              />
              <SummaryStat
                label="Actual-informed median"
                value={
                  actualRange
                    ? formatCurrency(actualRange.median, actualRange.currencyCode)
                    : "Not available"
                }
                hint={
                  actualRange
                    ? `Observed uplift ${formatPercent(actualRange.varianceMedianPct)}`
                    : "Complete actuals history is still too thin"
                }
              />
              <SummaryStat
                label="Actual-informed band"
                value={
                  actualRange
                    ? `${formatPercent(actualRange.varianceLowPct)} to ${formatPercent(actualRange.varianceHighPct)}`
                    : "Not available"
                }
                hint={
                  actualRange
                    ? `${actualRange.sampleSize} complete-project benchmarks`
                    : "Range appears once three complete actuals exist"
                }
              />
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <h3 className="text-sm font-semibold text-slate-900">Method</h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                {recommendationsData.methodologySummary}
              </p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-md bg-white p-3">
                  <p className="text-xs uppercase tracking-wide text-slate-500">
                    Quote sample
                  </p>
                  <p className="mt-1 text-sm font-medium text-slate-900">
                    {overallRange ? `${overallRange.sampleSize} projects` : "Suppressed"}
                  </p>
                </div>
                <div className="rounded-md bg-white p-3">
                  <p className="text-xs uppercase tracking-wide text-slate-500">
                    Actual sample
                  </p>
                  <p className="mt-1 text-sm font-medium text-slate-900">
                    {actualRange ? `${actualRange.sampleSize} projects` : "Limited"}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div>
            <div className="mb-3">
              <h3 className="text-sm font-semibold text-slate-900">Discipline ranges</h3>
              <p className="mt-1 text-sm text-slate-600">
                Discipline-level quoted medians, with observed variance where complete actuals exist.
              </p>
            </div>
            {recommendationsData.disciplineRanges.length > 0 ? (
              <DisciplineRangeTable disciplineRanges={recommendationsData.disciplineRanges} />
            ) : (
              <p className="rounded-lg border border-dashed border-slate-300 px-4 py-3 text-sm text-slate-600">
                No discipline-level range is available yet for this comparable set.
              </p>
            )}
          </div>
        </div>
      </SectionCard>

      <ProjectPredictiveGuidancePanel
        description="Weighted suggestions for likely quote position, discipline mix, monthly spread, and overrun exposure."
        predictiveGuidance={predictiveGuidanceData}
      />

      <SectionCard title="Recommendation Context" description={recommendationsData.methodologySummary}>
        <div className="space-y-3">
          {recommendationsData.riskSignals.map((riskSignal) => (
            <div className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 p-3" key={riskSignal.key}>
              <div>
                <p className="text-sm font-medium text-slate-900">{riskSignal.detail}</p>
                <p className="text-xs text-slate-500">{riskSignal.key}</p>
              </div>
              <StatusBadge value={riskSignal.severity} />
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Comparable Project Set" description="Review similarity signals, actual benchmarks, and manual pin or exclude decisions.">
        <div className="space-y-4">
          {comparablesData.items.map((item) => {
            const benchmark = item.benchmarkSummary;
            return (
              <div className="space-y-3 rounded-lg border border-slate-200 p-4" key={item.projectId}>
                <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-slate-900">{item.projectName}</p>
                      <StatusBadge value={item.status} />
                      {item.selectionState !== "auto" ? (
                        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700">
                          {item.selectionState === "pinned" ? "Pinned" : "Excluded"}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 text-sm text-slate-600">
                      {item.clientName ?? "Unknown client"} · Strength {item.strength} · Coverage{" "}
                      {formatPercent(item.coveragePct)}
                    </p>
                  </div>
                  <div className="grid gap-2 md:grid-cols-2">
                    <CheckboxField
                      checked={pinnedProjectIds.includes(item.projectId)}
                      label="Pinned"
                      onChange={(event) => {
                        setPinnedProjectIds((current) =>
                          event.target.checked
                            ? [...new Set([...current, item.projectId])]
                            : current.filter((value) => value !== item.projectId)
                        );
                      }}
                    />
                    <CheckboxField
                      checked={excludedProjectIds.includes(item.projectId)}
                      label="Excluded"
                      onChange={(event) => {
                        setExcludedProjectIds((current) =>
                          event.target.checked
                            ? [...new Set([...current, item.projectId])]
                            : current.filter((value) => value !== item.projectId)
                        );
                      }}
                    />
                  </div>
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  <SummaryStat label="Similarity" value={formatPercent(item.similarityScore)} />
                  <SummaryStat
                    label="Quoted amount"
                    value={
                      benchmark ? formatCurrency(benchmark.quotedAmount, benchmark.currencyCode) : "Not set"
                    }
                  />
                  <SummaryStat
                    label="Quote vs actual"
                    value={
                      benchmark?.quoteToActualVariancePct != null
                        ? formatPercent(benchmark.quoteToActualVariancePct)
                        : "Not available"
                    }
                  />
                </div>
                <p className="text-sm text-slate-600">
                  {item.isEligibleForRecommendations
                    ? "Included in numeric guidance when the comparable sample is large enough."
                    : "Visible for review, but excluded from numeric guidance because of status, currency, or selection state."}
                </p>
                {benchmark ? (
                  <div className="grid gap-3 md:grid-cols-3">
                    <SummaryStat
                      label="Actual amount"
                      value={
                        benchmark.actualAmount != null
                          ? formatCurrency(benchmark.actualAmount, benchmark.currencyCode)
                          : "Not available"
                      }
                    />
                    <SummaryStat
                      label="Actuals status"
                      value={benchmark.actualsStatus}
                      hint={
                        benchmark.actualsAsOfDate
                          ? `As of ${formatDate(benchmark.actualsAsOfDate)}`
                          : "No actuals date recorded"
                      }
                    />
                    <SummaryStat
                      label="Source quote version"
                      value={benchmark.sourceQuoteVersionId ?? "Not linked"}
                    />
                  </div>
                ) : null}
                {item.disciplineBenchmarkSummaries.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-separate border-spacing-0 text-sm">
                      <thead>
                        <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                          <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
                            Discipline
                          </th>
                          <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
                            Quoted
                          </th>
                          <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
                            Actual
                          </th>
                          <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
                            Variance
                          </th>
                          <th className="border-b border-slate-200 pb-2 font-medium">
                            Status
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {item.disciplineBenchmarkSummaries.map((summary) => (
                          <tr className="text-slate-700" key={`${item.projectId}-${summary.disciplineId}`}>
                            <td className="border-b border-slate-100 py-2.5 pr-4 font-medium text-slate-900">
                              {summary.disciplineName ?? summary.disciplineId}
                            </td>
                            <td className="border-b border-slate-100 py-2.5 pr-4">
                              {benchmark
                                ? formatCurrency(summary.quotedAmount, benchmark.currencyCode)
                                : "Not available"}
                            </td>
                            <td className="border-b border-slate-100 py-2.5 pr-4">
                              {summary.actualAmount != null && benchmark
                                ? formatCurrency(summary.actualAmount, benchmark.currencyCode)
                                : "Not available"}
                            </td>
                            <td className="border-b border-slate-100 py-2.5 pr-4">
                              {summary.quoteToActualVariancePct != null
                                ? formatPercent(summary.quoteToActualVariancePct)
                                : "Not available"}
                            </td>
                            <td className="border-b border-slate-100 py-2.5">
                              <StatusBadge value={summary.actualsStatus} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
                <div className="grid gap-2">
                  {item.matchedFactors.map((factor) => (
                    <div className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700" key={factor.factorKey}>
                      <strong>{factor.label}</strong>: {factor.detail}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
        <div className="mt-4">
          <TextAreaField
            label="Selection note"
            onChange={(event) => setNote(event.target.value)}
            value={note}
          />
          <div className="mt-4">
            <InlineActionBar>
              <Button onClick={() => selectionMutation.mutate()} type="button" variant="primary">
                {selectionMutation.isPending ? "Saving..." : "Save comparable selection"}
              </Button>
            </InlineActionBar>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
