import type { ProjectPredictiveGuidanceResponse } from "@quotes4/contracts";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SummaryStat } from "@/components/ui/summary-stat";
import {
  formatCurrency,
  formatDateTime,
  formatPercent,
  formatStatusLabel,
} from "@/lib/format";

function confidenceTone(confidence?: string) {
  if (confidence === "high") {
    return "positive" as const;
  }
  if (confidence === "low") {
    return "warning" as const;
  }
  return "default" as const;
}

function riskTone(level: string) {
  return level === "high" || level === "medium"
    ? ("warning" as const)
    : ("default" as const);
}

export function ProjectPredictiveGuidancePanel({
  predictiveGuidance,
  title = "Predictive Guidance",
  description = "Explainable suggestions built from comparable quotes, benchmark variance, and timing history.",
}: {
  predictiveGuidance: ProjectPredictiveGuidanceResponse;
  title?: string;
  description?: string;
}) {
  const likelyRange = predictiveGuidance.likelyQuoteRange;
  const currencyCode = predictiveGuidance.target.quoteCurrencyCode;
  const missingCriticalInputs = predictiveGuidance.missingCriticalInputs ?? [];

  return (
    <div className="space-y-6">
      <SectionCard
        title={title}
        description={description}
        actions={<StatusBadge value={predictiveGuidance.overrunRisk.level} />}
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <SummaryStat
            label="Likely quote median"
            value={
              likelyRange
                ? formatCurrency(likelyRange.median, likelyRange.currencyCode)
                : "Not available"
            }
            hint={
              likelyRange
                ? `${formatCurrency(likelyRange.low, likelyRange.currencyCode)} to ${formatCurrency(likelyRange.high, likelyRange.currencyCode)}`
                : "Comparable quote history is still too thin"
            }
            tone={confidenceTone(likelyRange?.confidence)}
          />
          <SummaryStat
            label="Prediction basis"
            value={
              likelyRange ? formatStatusLabel(likelyRange.basis) : "Not available"
            }
            hint={
              likelyRange
                ? `${formatStatusLabel(likelyRange.confidence)} confidence`
                : "Waiting on stronger comparable evidence"
            }
          />
          <SummaryStat
            label="Overrun risk"
            value={formatStatusLabel(predictiveGuidance.overrunRisk.level)}
            hint={`${predictiveGuidance.overrunRisk.flags.length} active flag(s)`}
            tone={riskTone(predictiveGuidance.overrunRisk.level)}
          />
          <SummaryStat
            label="Historical sample"
            value={predictiveGuidance.modelInfo.comparableProjectsUsed}
            hint={`${predictiveGuidance.modelInfo.completeActualHistoryCount} complete actuals, ${predictiveGuidance.modelInfo.monthlyProfileCount} monthly profiles`}
          />
          <SummaryStat
            label="Feature readiness"
            value={formatPercent(predictiveGuidance.featureReadinessScore)}
            hint={`${formatPercent(predictiveGuidance.dataSufficiencyScore)} data sufficiency`}
          />
          <SummaryStat
            label="Fallback tier"
            value={formatStatusLabel(predictiveGuidance.fallbackTier)}
            hint={formatStatusLabel(predictiveGuidance.primaryEvidenceSource)}
          />
          <SummaryStat
            label="Win probability"
            value={
              predictiveGuidance.winProbability
                ? formatPercent(predictiveGuidance.winProbability.probabilityPct)
                : "Not available"
            }
            hint={
              predictiveGuidance.winProbability
                ? `${formatStatusLabel(predictiveGuidance.winProbability.probabilityBand)} band`
                : "Requires bid-stage evidence"
            }
            tone={confidenceTone(predictiveGuidance.winProbability?.confidence)}
          />
          <SummaryStat
            label="Overrides"
            value={predictiveGuidance.overrides?.length ?? 0}
            hint={`${predictiveGuidance.scenarios?.length ?? 0} stored scenario(s)`}
          />
        </div>

        <div className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm font-medium text-slate-900">
            {predictiveGuidance.methodologySummary}
          </p>
          <p className="mt-2 text-sm text-slate-600">
            {predictiveGuidance.modelInfo.updateApproach}
          </p>
          <p className="mt-2 text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
            Refreshed {formatDateTime(predictiveGuidance.modelInfo.refreshedAt)}
          </p>
        </div>

        {missingCriticalInputs.length > 0 ? (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-900">
              Missing critical inputs
            </p>
            <p className="mt-2 text-sm text-amber-900">
              {missingCriticalInputs
                .map((item) => formatStatusLabel(item))
                .join(", ")}
            </p>
          </div>
        ) : null}
      </SectionCard>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <SectionCard
          title="Likely Discipline Usage"
          description="Historical discipline presence, share of quote value, and amount guidance for this project shape."
        >
          {predictiveGuidance.disciplineUsage.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                    <th className="px-4 py-3">Discipline</th>
                    <th className="px-4 py-3">Usage rate</th>
                    <th className="px-4 py-3">Likely share</th>
                    <th className="px-4 py-3">Likely amount</th>
                    <th className="px-4 py-3">Observed variance</th>
                    <th className="px-4 py-3">Confidence</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {predictiveGuidance.disciplineUsage.map((item) => (
                    <tr key={item.disciplineId}>
                      <td className="px-4 py-3">
                        <p className="font-medium text-slate-900">
                          {item.disciplineName ?? item.disciplineCode ?? item.disciplineId}
                        </p>
                        <p className="text-xs text-slate-500">
                          {item.isTargetDiscipline
                            ? "Tagged on target project"
                            : `${item.sampleSize} comparable projects`}
                        </p>
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {formatPercent(item.usageRatePct)}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {formatPercent(item.predictedSharePct)}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {item.predictedAmountMedian == null
                          ? "Not available"
                          : formatCurrency(item.predictedAmountMedian, currencyCode)}
                        {item.predictedAmountLow != null &&
                        item.predictedAmountHigh != null ? (
                          <p className="text-xs text-slate-500">
                            {formatCurrency(item.predictedAmountLow, currencyCode)} to{" "}
                            {formatCurrency(item.predictedAmountHigh, currencyCode)}
                          </p>
                        ) : null}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {item.observedVarianceMedianPct == null
                          ? "Not available"
                          : formatPercent(item.observedVarianceMedianPct)}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge value={item.confidence} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No discipline guidance yet"
              description="Comparable benchmark history is still too thin to estimate discipline usage."
            />
          )}
        </SectionCard>

        <SectionCard
          title="Likely Monthly Revenue Spread"
          description="Weighted monthly timing profile aligned to the target project's current schedule or forecast."
        >
          {predictiveGuidance.monthlyRevenueSpread.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                    <th className="px-4 py-3">Month</th>
                    <th className="px-4 py-3">Share band</th>
                    <th className="px-4 py-3">Likely amount</th>
                    <th className="px-4 py-3">Confidence</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {predictiveGuidance.monthlyRevenueSpread.map((item) => (
                    <tr key={item.month}>
                      <td className="px-4 py-3 font-medium text-slate-900">
                        {item.month}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {formatPercent(item.medianSharePct)}
                        <p className="text-xs text-slate-500">
                          {formatPercent(item.lowSharePct)} to{" "}
                          {formatPercent(item.highSharePct)}
                        </p>
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {item.predictedAmountMedian == null
                          ? "Not available"
                          : formatCurrency(item.predictedAmountMedian, currencyCode)}
                        {item.predictedAmountLow != null &&
                        item.predictedAmountHigh != null ? (
                          <p className="text-xs text-slate-500">
                            {formatCurrency(item.predictedAmountLow, currencyCode)} to{" "}
                            {formatCurrency(item.predictedAmountHigh, currencyCode)}
                          </p>
                        ) : null}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge value={item.confidence} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No monthly spread guidance yet"
              description="The target project or comparable history is missing enough timing structure to project monthly revenue spread."
            />
          )}
        </SectionCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <SectionCard
          title="Win Probability"
          description="Explainable bid-stage probability built from stage, account context, pricing position, and similar historical outcomes."
        >
          {predictiveGuidance.winProbability ? (
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                <SummaryStat
                  label="Probability"
                  value={formatPercent(predictiveGuidance.winProbability.probabilityPct)}
                  hint={formatStatusLabel(predictiveGuidance.winProbability.probabilityBand)}
                  tone={confidenceTone(predictiveGuidance.winProbability.confidence)}
                />
                <SummaryStat
                  label="Confidence"
                  value={formatStatusLabel(predictiveGuidance.winProbability.confidence)}
                  hint={`${predictiveGuidance.winProbability.confidenceScore.toFixed(1)} confidence score`}
                />
                <SummaryStat
                  label="Override"
                  value={formatStatusLabel(predictiveGuidance.winProbability.overrideStatus ?? "none")}
                  hint={formatStatusLabel(predictiveGuidance.winProbability.fallbackTier)}
                />
              </div>
              <div className="space-y-3">
                {predictiveGuidance.winProbability.keyFactors.map((factor) => (
                  <div className="rounded-lg border border-slate-200 bg-white p-4" key={factor.key}>
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-slate-900">{factor.label}</p>
                      <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                        {factor.effect > 0 ? "+" : ""}
                        {factor.effect.toFixed(1)}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-slate-600">{factor.detail}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState
              title="No win probability yet"
              description="This project does not yet have enough bid-stage context for a reliable win-probability view."
            />
          )}
        </SectionCard>

        <SectionCard
          title="Comparable Evidence"
          description="Top persisted comparable references used by the latest expected scenario."
        >
          {predictiveGuidance.topComparables?.length ? (
            <div className="space-y-3">
              {predictiveGuidance.topComparables.slice(0, 5).map((item) => (
                <div className="rounded-lg border border-slate-200 bg-white p-4" key={`${item.projectId}-${item.projectName}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{item.projectName}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {formatPercent(item.similarityScore)} similarity · {formatStatusLabel(item.selectionState)}
                      </p>
                    </div>
                    <StatusBadge value={item.strength} />
                  </div>
                  {item.evidence?.length ? (
                    <p className="mt-2 text-sm text-slate-600">
                      {item.evidence.slice(0, 2).map((factor) => factor.detail).join(" ")}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No comparable evidence stored"
              description="Create or refresh a prediction run to capture comparable evidence and audit detail."
            />
          )}
        </SectionCard>
      </div>

      <SectionCard
        title="Overrun Risk Flags"
        description="Actionable flags derived from historical quote-to-actual variance, current forecast position, and concentration patterns."
      >
        <div className="space-y-4">
          {predictiveGuidance.overrunRisk.flags.length > 0 ? (
            predictiveGuidance.overrunRisk.flags.map((flag) => (
              <div
                className="rounded-lg border border-slate-200 bg-white p-4"
                key={flag.key}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">
                      {flag.title}
                    </p>
                    <p className="mt-1 text-sm text-slate-600">{flag.detail}</p>
                    <p className="mt-2 text-xs text-slate-500">
                      {flag.reasoning.join(" ")}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <StatusBadge value={flag.severity} />
                    <StatusBadge value={flag.confidence} />
                  </div>
                </div>
              </div>
            ))
          ) : (
            <EmptyState
              title="No active overrun flags"
              description="Historical variance and current project signals do not currently point to an elevated overrun risk."
            />
          )}

          {predictiveGuidance.riskSignals.length > 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4">
              <h3 className="text-sm font-semibold text-slate-900">
                Data quality signals
              </h3>
              <div className="mt-3 space-y-3">
                {predictiveGuidance.riskSignals.map((signal) => (
                  <div
                    className="flex items-start justify-between gap-3"
                    key={signal.key}
                  >
                    <div>
                      <p className="text-sm text-slate-700">{signal.detail}</p>
                      <p className="text-xs text-slate-500">{signal.key}</p>
                    </div>
                    <StatusBadge value={signal.severity} />
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </SectionCard>
    </div>
  );
}
