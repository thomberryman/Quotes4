"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import { getBrowserApiClient } from "@/lib/api/browser-client";
import { formatCurrency, formatPercent } from "@/lib/format";
import { queryKeys } from "@/lib/query/keys";

import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { SummaryStat } from "@/components/ui/summary-stat";

import { DisciplineRangeTable } from "./dashboard-charts";

export function ProjectBenchmarkPanel({
  projectId,
  projectLabel,
}: {
  projectId: string | undefined;
  projectLabel: string | undefined;
}) {
  const api = getBrowserApiClient();

  const comparablesQuery = useQuery({
    enabled: Boolean(projectId),
    placeholderData: (previousData) => previousData,
    queryFn: async () => {
      if (!projectId) {
        return null;
      }

      return api.getProjectComparables(projectId, {
        includePinned: true,
        limit: 10,
      });
    },
    queryKey: projectId
      ? queryKeys.projectComparables(projectId)
      : ["project-comparables", "dashboard-empty"],
  });

  const recommendationsQuery = useQuery({
    enabled: Boolean(projectId),
    placeholderData: (previousData) => previousData,
    queryFn: async () => {
      if (!projectId) {
        return null;
      }

      return api.getProjectRecommendations(projectId, { limit: 10 });
    },
    queryKey: projectId
      ? queryKeys.projectRecommendations(projectId)
      : ["project-recommendations", "dashboard-empty"],
  });

  if (!projectId) {
    return (
      <SectionCard
        title="Project Benchmark Detail"
        description="Choose one project in the filters to open explainable comparable ranges and recommendations."
      >
        <EmptyState
          title="Narrow to one project"
          description="The benchmark detail panel stays project-specific so the recommendation logic remains explainable and reviewable."
        />
      </SectionCard>
    );
  }

  if (comparablesQuery.error || recommendationsQuery.error) {
    return (
      <SectionCard
        title="Project Benchmark Detail"
        description={`Comparable ranges for ${projectLabel ?? projectId}.`}
      >
        <ErrorState
          title="Benchmark detail unavailable"
          description="The comparable project detail could not be loaded for the selected project."
        />
      </SectionCard>
    );
  }

  if (
    comparablesQuery.isLoading ||
    recommendationsQuery.isLoading ||
    !comparablesQuery.data ||
    !recommendationsQuery.data
  ) {
    return (
      <SectionCard
        title="Project Benchmark Detail"
        description={`Comparable ranges for ${projectLabel ?? projectId}.`}
      >
        <div className="grid gap-4 md:grid-cols-3">
          <div className="h-28 animate-pulse rounded-xl bg-slate-100" />
          <div className="h-28 animate-pulse rounded-xl bg-slate-100" />
          <div className="h-28 animate-pulse rounded-xl bg-slate-100" />
        </div>
      </SectionCard>
    );
  }

  const comparables = comparablesQuery.data.items.slice(0, 5);
  const quoteRange = recommendationsQuery.data.overallQuoteRange;
  const actualInformedRange = recommendationsQuery.data.overallActualInformedRange;

  return (
    <SectionCard
      title="Project Benchmark Detail"
      description={`Comparable ranges and recommendation context for ${projectLabel ?? projectId}.`}
      actions={
        <Link
          className="inline-flex items-center justify-center rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-900 transition hover:bg-slate-50"
          href={`/projects/${projectId}/comparables`}
        >
          Open full comparables review
        </Link>
      }
    >
      <div className="space-y-6">
        <div className="grid gap-4 md:grid-cols-4">
          <SummaryStat
            label="Comparable set"
            value={recommendationsQuery.data.comparablesUsed.length}
            hint="Projects used in the recommendation set"
          />
          <SummaryStat
            label="Quoted median"
            value={
              quoteRange
                ? formatCurrency(quoteRange.median, quoteRange.currencyCode)
                : "Not available"
            }
            hint={
              quoteRange
                ? `${formatCurrency(quoteRange.low, quoteRange.currencyCode)} to ${formatCurrency(quoteRange.high, quoteRange.currencyCode)}`
                : "Needs a larger comparable sample"
            }
          />
          <SummaryStat
            label="Actual-informed median"
            value={
              actualInformedRange
                ? formatCurrency(
                    actualInformedRange.median,
                    actualInformedRange.currencyCode,
                  )
                : "Not available"
            }
            hint={
              actualInformedRange
                ? `Observed variance median ${formatPercent(actualInformedRange.varianceMedianPct)}`
                : "No complete actuals benchmark range yet"
            }
          />
          <SummaryStat
            label="Risk signals"
            value={comparablesQuery.data.riskSignals.length}
            hint="Explainable constraints carried into the recommendation"
          />
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">
                Discipline Ranges
              </h3>
              <p className="mt-1 text-sm text-slate-600">
                Quote benchmarks by discipline, including median observed variance
                where actuals exist.
              </p>
            </div>
            <DisciplineRangeTable
              disciplineRanges={recommendationsQuery.data.disciplineRanges}
            />
          </div>

          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">
                Recommendation Context
              </h3>
              <p className="mt-1 text-sm text-slate-600">
                {recommendationsQuery.data.methodologySummary}
              </p>
            </div>
            <div className="space-y-3">
              {recommendationsQuery.data.riskSignals.map((riskSignal) => (
                <div
                  className="rounded-xl border border-slate-200 bg-slate-50 p-4"
                  key={riskSignal.key}
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-medium text-slate-900">{riskSignal.detail}</p>
                    <span
                      className={
                        riskSignal.severity === "high"
                          ? "rounded-full bg-rose-100 px-2.5 py-1 text-xs font-semibold text-rose-700"
                          : riskSignal.severity === "medium"
                            ? "rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-700"
                            : "rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700"
                      }
                    >
                      {riskSignal.severity}
                    </span>
                  </div>
                  <p className="mt-2 text-xs uppercase tracking-wide text-slate-500">
                    {riskSignal.key}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">
              Top comparable projects
            </h3>
            <p className="mt-1 text-sm text-slate-600">
              Highest-scoring comparable candidates with coverage and benchmark
              context.
            </p>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {comparables.map((item) => (
              <div
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
                key={item.projectId}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-slate-900">{item.projectName}</p>
                    <p className="mt-1 text-sm text-slate-600">
                      {item.clientName ?? "Unknown client"} · {item.strength} match
                    </p>
                  </div>
                  <div className="text-right text-sm">
                    <p className="font-medium text-slate-900">
                      {formatPercent(item.similarityScore)}
                    </p>
                    <p className="text-slate-500">
                      Coverage {formatPercent(item.coveragePct)}
                    </p>
                  </div>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <SummaryStat
                    label="Quoted amount"
                    value={
                      item.benchmarkSummary
                        ? formatCurrency(
                            item.benchmarkSummary.quotedAmount,
                            item.benchmarkSummary.currencyCode,
                          )
                        : "Not available"
                    }
                  />
                  <SummaryStat
                    label="Quote vs actual"
                    value={
                      item.benchmarkSummary?.quoteToActualVariancePct == null
                        ? "Not available"
                        : formatPercent(
                            item.benchmarkSummary.quoteToActualVariancePct,
                          )
                    }
                  />
                </div>
                <div className="mt-4 space-y-2 text-sm text-slate-600">
                  {item.matchedFactors.slice(0, 3).map((factor) => (
                    <p key={factor.factorKey}>
                      <span className="font-medium text-slate-900">
                        {factor.label}:
                      </span>{" "}
                      {factor.detail}
                    </p>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </SectionCard>
  );
}
