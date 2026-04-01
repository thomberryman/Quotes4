import type {
  ProjectActualsVsQuoteRead,
  ProjectPredictiveGuidanceResponse,
} from "@quotes4/contracts";

import { ProjectPredictiveGuidancePanel } from "@/components/features/projects/project-predictive-guidance-panel";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SummaryStat } from "@/components/ui/summary-stat";
import { formatCurrency, formatDate, formatPercent } from "@/lib/format";

function varianceTone(value: number | null | undefined) {
  if (value == null || value === 0) {
    return "default" as const;
  }
  return value > 0 ? ("warning" as const) : ("positive" as const);
}

export function ProjectActualsVsQuoteWorkspace({
  projectActualsVsQuote,
  predictiveGuidance,
}: {
  projectActualsVsQuote: ProjectActualsVsQuoteRead;
  predictiveGuidance: ProjectPredictiveGuidanceResponse;
}) {
  const benchmarkSummary = projectActualsVsQuote.benchmarkSummary;

  if (benchmarkSummary == null) {
    return (
      <SectionCard
        title="Quote vs Actual"
        description="Project-level variance appears once a benchmark summary has been generated for this project."
      >
        <EmptyState
          title="No benchmark summary yet"
          description="Approved quote and actual benchmark data has not been generated for this project yet."
        />
      </SectionCard>
    );
  }

  return (
    <div className="space-y-6">
      <SectionCard
        title="Project Benchmark Summary"
        description="Quoted versus actual totals, traceability status, and benchmark lineage for this project."
        actions={<StatusBadge value={benchmarkSummary.actualsStatus} />}
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <SummaryStat
            label="Quoted amount"
            value={formatCurrency(
              benchmarkSummary.quotedAmount,
              benchmarkSummary.currencyCode,
            )}
          />
          <SummaryStat
            label="Actual amount"
            value={
              benchmarkSummary.actualAmount == null
                ? "Not available"
                : formatCurrency(
                    benchmarkSummary.actualAmount,
                    benchmarkSummary.currencyCode,
                  )
            }
          />
          <SummaryStat
            label="Variance amount"
            value={
              benchmarkSummary.quoteToActualVarianceAmount == null
                ? "Not available"
                : formatCurrency(
                    benchmarkSummary.quoteToActualVarianceAmount,
                    benchmarkSummary.currencyCode,
                  )
            }
            tone={varianceTone(benchmarkSummary.quoteToActualVarianceAmount)}
          />
          <SummaryStat
            label="Variance percent"
            value={
              benchmarkSummary.quoteToActualVariancePct == null
                ? "Not available"
                : formatPercent(benchmarkSummary.quoteToActualVariancePct)
            }
            tone={varianceTone(benchmarkSummary.quoteToActualVariancePct)}
            hint={
              benchmarkSummary.actualsAsOfDate
                ? `Actuals as of ${formatDate(benchmarkSummary.actualsAsOfDate)}`
                : "No actuals as-of date recorded"
            }
          />
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
              Source quote version
            </p>
            <p className="mt-2 text-sm font-medium text-slate-900">
              {benchmarkSummary.sourceQuoteVersionId ?? "Not linked"}
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
              Actuals status
            </p>
            <div className="mt-2">
              <StatusBadge value={benchmarkSummary.actualsStatus} />
            </div>
          </div>
        </div>
      </SectionCard>

      <ProjectPredictiveGuidancePanel
        description="Forward-looking guidance derived from the same comparable and variance history used in the benchmark view."
        predictiveGuidance={predictiveGuidance}
        title="Forward Guidance"
      />

      <SectionCard
        title="Discipline Breakdown"
        description="Discipline-level quoted, actual, and variance values from the persisted project benchmark summary."
      >
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead>
              <tr className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                <th className="px-4 py-3">Discipline</th>
                <th className="px-4 py-3">Quoted</th>
                <th className="px-4 py-3">Actual</th>
                <th className="px-4 py-3">Variance</th>
                <th className="px-4 py-3">Variance %</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 bg-white">
              {benchmarkSummary.disciplineSummaries.map((summary) => (
                <tr key={summary.disciplineId}>
                  <td className="px-4 py-3 font-medium text-slate-900">
                    {summary.disciplineName ?? summary.disciplineId}
                  </td>
                  <td className="px-4 py-3 text-slate-700">
                    {formatCurrency(
                      summary.quotedAmount,
                      benchmarkSummary.currencyCode,
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-700">
                    {summary.actualAmount == null
                      ? "Not available"
                      : formatCurrency(
                          summary.actualAmount,
                          benchmarkSummary.currencyCode,
                        )}
                  </td>
                  <td className="px-4 py-3 text-slate-700">
                    {summary.quoteToActualVarianceAmount == null
                      ? "Not available"
                      : formatCurrency(
                          summary.quoteToActualVarianceAmount,
                          benchmarkSummary.currencyCode,
                        )}
                  </td>
                  <td className="px-4 py-3 text-slate-700">
                    {summary.quoteToActualVariancePct == null
                      ? "Not available"
                      : formatPercent(summary.quoteToActualVariancePct)}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge value={summary.actualsStatus} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}
