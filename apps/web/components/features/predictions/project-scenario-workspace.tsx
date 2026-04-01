"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import type {
  PredictionRunDetailRead,
  PredictionRunSummaryRead,
  PredictionScenarioRead,
  ProjectRead,
} from "@quotes4/contracts";
import { ApiClientError } from "@quotes4/contracts";

import { getBrowserApiClient } from "@/lib/api/browser-client";
import { formatCurrency, formatDateTime, formatPercent, formatStatusLabel } from "@/lib/format";
import { queryKeys } from "@/lib/query/keys";

import { InlineActionBar } from "@/components/forms/inline-action-bar";
import { SelectField } from "@/components/forms/select-field";
import { TextInput } from "@/components/forms/text-input";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SummaryStat } from "@/components/ui/summary-stat";
import { Button } from "@/components/ui/button";

type ScenarioDraft = {
  quoteMultiplier: string;
  actualMultiplier: string;
  varianceDeltaPct: string;
  winProbabilityDeltaPct: string;
  scheduleShiftMonths: string;
};

function toStringValue(value: unknown, fallback: string): string {
  if (typeof value === "number") {
    return String(value);
  }
  if (typeof value === "string" && value.length > 0) {
    return value;
  }
  return fallback;
}

function toScenarioDraft(scenario: PredictionScenarioRead | undefined): ScenarioDraft {
  const overrides = scenario?.assumptionOverrides ?? {};
  return {
    quoteMultiplier: toStringValue(overrides.quoteMultiplier, "1"),
    actualMultiplier: toStringValue(overrides.actualMultiplier, "1"),
    varianceDeltaPct: toStringValue(overrides.varianceDeltaPct, "0"),
    winProbabilityDeltaPct: toStringValue(overrides.winProbabilityDeltaPct, "0"),
    scheduleShiftMonths: toStringValue(overrides.scheduleShiftMonths, "0"),
  };
}

function numberFromDraft(value: string, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function boolSelectValue(value: boolean | undefined) {
  return value ? "yes" : "no";
}

export function ProjectScenarioWorkspace({
  initialProject,
  initialRun,
  initialRunList,
  projectId,
}: {
  initialProject: ProjectRead;
  initialRun: PredictionRunDetailRead;
  initialRunList: PredictionRunSummaryRead[];
  projectId: string;
}) {
  const api = getBrowserApiClient();
  const queryClient = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState(initialRun.id);
  const [selectedScenarioKey, setSelectedScenarioKey] = useState(
    initialRun.expectedScenarioKey ?? "base",
  );
  const [scenarioDraft, setScenarioDraft] = useState<ScenarioDraft>(
    toScenarioDraft(
      initialRun.scenarios?.find((item) => item.scenarioKey === initialRun.expectedScenarioKey) ??
        initialRun.scenarios?.[0],
    ),
  );
  const [quoteAcceptanceStatus, setQuoteAcceptanceStatus] = useState("partial_accept");
  const [quoteRecommendedLow, setQuoteRecommendedLow] = useState(
    String(initialRun.likelyQuoteRange?.recommendedLow ?? initialRun.likelyQuoteRange?.low ?? ""),
  );
  const [quoteRecommendedMedian, setQuoteRecommendedMedian] = useState(
    String(initialRun.likelyQuoteRange?.recommendedMedian ?? initialRun.likelyQuoteRange?.median ?? ""),
  );
  const [quoteRecommendedHigh, setQuoteRecommendedHigh] = useState(
    String(initialRun.likelyQuoteRange?.recommendedHigh ?? initialRun.likelyQuoteRange?.high ?? ""),
  );
  const [winOverrideStatus, setWinOverrideStatus] = useState("manual_override");
  const [winProbabilityPct, setWinProbabilityPct] = useState(
    String(initialRun.winProbability?.probabilityPct ?? ""),
  );
  const [metadataProjectFormatKey, setMetadataProjectFormatKey] = useState(
    initialProject.metadata?.projectFormatKey ?? initialProject.metadata?.formatType ?? "",
  );
  const [metadataDurationWeeks, setMetadataDurationWeeks] = useState(
    String(initialProject.metadata?.durationWeeks ?? ""),
  );
  const [metadataEpisodeCount, setMetadataEpisodeCount] = useState(
    String(initialProject.metadata?.episodeCount ?? ""),
  );
  const [metadataGenre, setMetadataGenre] = useState(initialProject.metadata?.genre ?? "");
  const [metadataLanguage, setMetadataLanguage] = useState(initialProject.metadata?.language ?? "");
  const [metadataBudgetTarget, setMetadataBudgetTarget] = useState(
    String(initialProject.metadata?.budgetTarget ?? ""),
  );
  const [pipelineStageKey, setPipelineStageKey] = useState(initialProject.pipelineStageKey ?? "");
  const [strategicAccountFlag, setStrategicAccountFlag] = useState(
    boolSelectValue(initialProject.strategicAccountFlag),
  );
  const [promotionTitle, setPromotionTitle] = useState("");
  const [promotionProbability, setPromotionProbability] = useState(
    String(initialRun.winProbability?.probabilityPct ?? 100),
  );
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runListQuery = useQuery({
    initialData: { items: initialRunList },
    queryFn: async () => api.listPredictionRuns(projectId),
    queryKey: queryKeys.predictionRuns(projectId),
  });

  const runQuery = useQuery({
    enabled: Boolean(selectedRunId),
    initialData: selectedRunId === initialRun.id ? initialRun : undefined,
    queryFn: async () => api.getPredictionRun(projectId, selectedRunId),
    queryKey: queryKeys.predictionRun(projectId, selectedRunId),
  });

  const projectQuery = useQuery({
    initialData: initialProject,
    queryFn: async () => api.getProject(projectId),
    queryKey: queryKeys.project(projectId),
  });

  const project = projectQuery.data ?? initialProject;
  const run = runQuery.data ?? initialRun;
  const missingCriticalInputs = run.missingCriticalInputs ?? [];
  const selectedScenario =
    run.scenarios?.find((item) => item.scenarioKey === selectedScenarioKey) ??
    run.scenarios?.[0];

  useEffect(() => {
    if (!selectedScenario) {
      return;
    }
    setScenarioDraft(toScenarioDraft(selectedScenario));
  }, [selectedScenario]);

  useEffect(() => {
    setPipelineStageKey(project.pipelineStageKey ?? "");
    setStrategicAccountFlag(boolSelectValue(project.strategicAccountFlag));
    setMetadataProjectFormatKey(project.metadata?.projectFormatKey ?? project.metadata?.formatType ?? "");
    setMetadataDurationWeeks(String(project.metadata?.durationWeeks ?? ""));
    setMetadataEpisodeCount(String(project.metadata?.episodeCount ?? ""));
    setMetadataGenre(project.metadata?.genre ?? "");
    setMetadataLanguage(project.metadata?.language ?? "");
    setMetadataBudgetTarget(String(project.metadata?.budgetTarget ?? ""));
  }, [project]);

  useEffect(() => {
    setQuoteRecommendedLow(
      String(run.likelyQuoteRange?.recommendedLow ?? run.likelyQuoteRange?.low ?? ""),
    );
    setQuoteRecommendedMedian(
      String(run.likelyQuoteRange?.recommendedMedian ?? run.likelyQuoteRange?.median ?? ""),
    );
    setQuoteRecommendedHigh(
      String(run.likelyQuoteRange?.recommendedHigh ?? run.likelyQuoteRange?.high ?? ""),
    );
    setWinProbabilityPct(String(run.winProbability?.probabilityPct ?? ""));
    setPromotionProbability(String(run.winProbability?.probabilityPct ?? 100));
  }, [run]);

  const clearFeedback = () => {
    setError(null);
    setNotice(null);
  };

  const refreshPredictionQueries = async (runId?: string) => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.predictionRuns(projectId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.projectPredictiveGuidance(projectId) }),
      runId
        ? queryClient.invalidateQueries({ queryKey: queryKeys.predictionRun(projectId, runId) })
        : Promise.resolve(),
    ]);
  };

  const createRunMutation = useMutation({
    mutationFn: async () => api.createPredictionRun(projectId, { limit: 25 }),
    onMutate: clearFeedback,
    onSuccess: async (run) => {
      setSelectedRunId(run.id);
      setSelectedScenarioKey(run.expectedScenarioKey ?? "base");
      setNotice(`Created prediction run ${run.id.slice(0, 8)} with refreshed evidence.`);
      await refreshPredictionQueries(run.id);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not create the prediction run.",
      );
    },
  });

  const saveProjectSignalsMutation = useMutation({
    mutationFn: async () =>
      api.updateProject(projectId, {
        expectedUpdatedAt: projectQuery.data.updatedAt,
        pipelineStageKey: pipelineStageKey || null,
        strategicAccountFlag: strategicAccountFlag === "yes",
      }),
    onMutate: clearFeedback,
    onSuccess: async () => {
      setNotice("Saved project-level commercial signals. Refresh the run to apply them.");
      await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) });
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not save the project-level predictive signals.",
      );
    },
  });

  const saveMetadataMutation = useMutation({
    mutationFn: async () =>
      api.putProjectMetadata(projectId, {
        expectedUpdatedAt: projectQuery.data.updatedAt,
        projectFormatKey: metadataProjectFormatKey || null,
        durationWeeks: metadataDurationWeeks ? Number(metadataDurationWeeks) : null,
        episodeCount: metadataEpisodeCount ? Number(metadataEpisodeCount) : null,
        genre: metadataGenre || null,
        language: metadataLanguage || null,
        budgetTarget: metadataBudgetTarget ? Number(metadataBudgetTarget) : null,
        metadata: projectQuery.data.metadata?.metadata ?? null,
      }),
    onMutate: clearFeedback,
    onSuccess: async () => {
      setNotice("Saved project metadata signals. Refresh the run to apply them.");
      await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) });
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not save the project metadata signals.",
      );
    },
  });

  const saveScenarioMutation = useMutation({
    mutationFn: async () => {
      if (!selectedScenario || !selectedScenario.updatedAt) {
        throw new Error("Scenario timestamp missing.");
      }
      return api.updatePredictionScenario(projectId, run.id, selectedScenario.scenarioKey, {
        expectedUpdatedAt: selectedScenario.updatedAt,
        assumptionOverrides: {
          quoteMultiplier: numberFromDraft(scenarioDraft.quoteMultiplier, 1),
          actualMultiplier: numberFromDraft(scenarioDraft.actualMultiplier, 1),
          varianceDeltaPct: numberFromDraft(scenarioDraft.varianceDeltaPct, 0),
          winProbabilityDeltaPct: numberFromDraft(scenarioDraft.winProbabilityDeltaPct, 0),
          scheduleShiftMonths: Math.round(numberFromDraft(scenarioDraft.scheduleShiftMonths, 0)),
        },
      });
    },
    onMutate: clearFeedback,
    onSuccess: async (run) => {
      setNotice(`Saved ${formatStatusLabel(selectedScenarioKey)} scenario assumptions.`);
      await refreshPredictionQueries(run.id);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not save the scenario assumptions.",
      );
    },
  });

  const saveOverridesMutation = useMutation({
    mutationFn: async () =>
      api.patchPredictionOverrides(projectId, run.id, {
        items: [
          {
            moduleKey: "quote_guidance",
            targetKey: "overall_quote",
            status: quoteAcceptanceStatus,
            overrideValue: {
              recommendedLow: Number(quoteRecommendedLow),
              recommendedMedian: Number(quoteRecommendedMedian),
              recommendedHigh: Number(quoteRecommendedHigh),
            },
            note: "Saved from scenario planning workspace.",
          },
          {
            moduleKey: "win_probability",
            targetKey: "win_probability",
            status: winOverrideStatus,
            overrideValue: {
              probabilityPct: Number(winProbabilityPct),
            },
            note: "Saved from scenario planning workspace.",
          },
        ],
      }),
    onMutate: clearFeedback,
    onSuccess: async (run) => {
      setNotice("Saved quote and win-probability overrides.");
      await refreshPredictionQueries(run.id);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not save the override decisions.",
      );
    },
  });

  const promoteScenarioMutation = useMutation({
    mutationFn: async () =>
      api.promotePredictionScenario(projectId, run.id, {
        scenarioKey: selectedScenario?.scenarioKey ?? "base",
        title: promotionTitle || `${project.name} ${formatStatusLabel(selectedScenarioKey)} scenario`,
        notesText: "Promoted from the scenario planning workspace.",
        revisionReason: "Prediction scenario promotion",
        probabilityPercent: Number(promotionProbability),
      }),
    onMutate: clearFeedback,
    onSuccess: async (result) => {
      setNotice(
        `Promoted ${formatStatusLabel(result.scenarioKey)} to forecast draft ${result.promotedForecastVersionId.slice(0, 8)}.`,
      );
      await Promise.all([
        refreshPredictionQueries(run.id),
        queryClient.invalidateQueries({ queryKey: queryKeys.projectForecast(projectId) }),
      ]);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not promote the selected scenario into a forecast draft.",
      );
    },
  });

  const currencyCode =
    selectedScenario?.likelyQuoteRange?.currencyCode ?? run.target.quoteCurrencyCode ?? "GBP";

  return (
    <div className="space-y-6">
      {error ? <ErrorState title="Prediction workflow failed" description={error} /> : null}
      {notice ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          {notice}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryStat
          label="Expected quote median"
          value={
            selectedScenario?.likelyQuoteRange
              ? formatCurrency(selectedScenario.likelyQuoteRange.recommendedMedian ?? selectedScenario.likelyQuoteRange.median, currencyCode)
              : "Not available"
          }
          hint={selectedScenario?.likelyQuoteRange ? formatStatusLabel(selectedScenario.likelyQuoteRange.basis) : "No quote range yet"}
        />
        <SummaryStat
          label="Win probability"
          value={
            selectedScenario?.winProbability
              ? formatPercent(selectedScenario.winProbability.probabilityPct)
              : "Not available"
          }
          hint={
            selectedScenario?.winProbability
              ? `${formatStatusLabel(selectedScenario.winProbability.probabilityBand)} band`
              : "No bid-stage probability yet"
          }
        />
        <SummaryStat
          label="Feature readiness"
          value={formatPercent(run.featureReadinessScore)}
          hint={`${formatPercent(run.dataSufficiencyScore)} data sufficiency`}
        />
        <SummaryStat
          label="Fallback tier"
          value={formatStatusLabel(run.fallbackTier)}
          hint={`${run.modelInfo.comparableProjectsUsed} comparable projects used`}
        />
      </div>

      <SectionCard
        title="Prediction Runs"
        description="Persisted prediction runs keep explainability, overrides, and scenario changes auditable."
        actions={
          <Button
            onClick={() => createRunMutation.mutate()}
            type="button"
            variant="primary"
          >
            {createRunMutation.isPending ? "Refreshing..." : "Refresh prediction run"}
          </Button>
        }
      >
        <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
          <div className="space-y-3">
            {runListQuery.data.items.map((item) => {
              const active = item.id === selectedRunId;
              return (
                <button
                  className={`w-full rounded-lg border px-4 py-3 text-left transition ${
                    active
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-slate-200 bg-white text-slate-900 hover:border-slate-300"
                  }`}
                  key={item.id}
                  onClick={() => setSelectedRunId(item.id)}
                  type="button"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold">
                      {formatDateTime(item.generatedAt)}
                    </p>
                    <StatusBadge value={item.confidenceLabel} />
                  </div>
                  <p className={`mt-2 text-xs ${active ? "text-slate-200" : "text-slate-500"}`}>
                    {formatStatusLabel(item.maturityStage)} · {formatStatusLabel(item.primaryEvidenceSource)}
                  </p>
                </button>
              );
            })}
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm font-semibold text-slate-900">{run.methodologySummary}</p>
            <p className="mt-2 text-sm text-slate-600">{run.modelInfo.updateApproach}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <StatusBadge value={run.confidenceLabel} />
              <StatusBadge value={run.maturityStage} />
              <StatusBadge value={run.primaryEvidenceSource} />
            </div>
            {missingCriticalInputs.length > 0 ? (
              <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-900">
                  Missing critical inputs
                </p>
                <p className="mt-2 text-sm text-amber-900">
                  {missingCriticalInputs.map((item) => formatStatusLabel(item)).join(", ")}
                </p>
              </div>
            ) : null}
          </div>
        </div>
      </SectionCard>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <SectionCard
          title="Project Signals"
          description="Capture the structured project and commercial inputs that most strongly affect fallbacks, confidence, and win probability."
        >
          <div className="grid gap-4 md:grid-cols-2">
            <TextInput
              label="Pipeline stage key"
              onChange={(event) => setPipelineStageKey(event.target.value)}
              value={pipelineStageKey}
            />
            <SelectField
              label="Strategic account"
              onChange={(event) => setStrategicAccountFlag(event.target.value)}
              value={strategicAccountFlag}
            >
              <option value="no">No</option>
              <option value="yes">Yes</option>
            </SelectField>
            <TextInput
              label="Project format key"
              onChange={(event) => setMetadataProjectFormatKey(event.target.value)}
              value={metadataProjectFormatKey}
            />
            <TextInput
              label="Duration weeks"
              onChange={(event) => setMetadataDurationWeeks(event.target.value)}
              step="1"
              type="number"
              value={metadataDurationWeeks}
            />
            <TextInput
              label="Episode count"
              onChange={(event) => setMetadataEpisodeCount(event.target.value)}
              step="1"
              type="number"
              value={metadataEpisodeCount}
            />
            <TextInput
              label="Budget target"
              onChange={(event) => setMetadataBudgetTarget(event.target.value)}
              step="0.01"
              type="number"
              value={metadataBudgetTarget}
            />
            <TextInput
              label="Genre"
              onChange={(event) => setMetadataGenre(event.target.value)}
              value={metadataGenre}
            />
            <TextInput
              label="Language"
              onChange={(event) => setMetadataLanguage(event.target.value)}
              value={metadataLanguage}
            />
          </div>
          <InlineActionBar>
            <Button
              onClick={() => saveProjectSignalsMutation.mutate()}
              type="button"
              variant="secondary"
            >
              {saveProjectSignalsMutation.isPending ? "Saving..." : "Save project signals"}
            </Button>
            <Button
              onClick={() => saveMetadataMutation.mutate()}
              type="button"
              variant="primary"
            >
              {saveMetadataMutation.isPending ? "Saving..." : "Save metadata signals"}
            </Button>
          </InlineActionBar>
        </SectionCard>

        <SectionCard
          title="Comparable Evidence"
          description="Top comparable projects referenced by the current run and the strength of their match."
        >
          <div className="space-y-3">
            {run.topComparables?.length ? (
              run.topComparables.slice(0, 5).map((item) => (
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
              ))
            ) : (
              <EmptyState
                title="No comparable evidence persisted"
                description="Refresh the run after comparable selection or metadata updates."
              />
            )}
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="Scenario Planning"
        description="Adjust the explicit levers that shape quote range, usage, timing, variance, and weighted revenue."
      >
        <div className="flex flex-wrap gap-2">
          {(run.scenarios ?? []).map((item) => {
            const active = item.scenarioKey === selectedScenarioKey;
            return (
              <button
                className={`rounded-lg px-3 py-2 text-sm font-medium transition ${
                  active
                    ? "bg-slate-900 text-white"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
                key={item.scenarioKey}
                onClick={() => setSelectedScenarioKey(item.scenarioKey)}
                type="button"
              >
                {item.title}
              </button>
            );
          })}
        </div>

        {selectedScenario ? (
          <>
            <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
              <TextInput
                label="Quote multiplier"
                onChange={(event) =>
                  setScenarioDraft((current) => ({
                    ...current,
                    quoteMultiplier: event.target.value,
                  }))
                }
                step="0.01"
                type="number"
                value={scenarioDraft.quoteMultiplier}
              />
              <TextInput
                label="Actual multiplier"
                onChange={(event) =>
                  setScenarioDraft((current) => ({
                    ...current,
                    actualMultiplier: event.target.value,
                  }))
                }
                step="0.01"
                type="number"
                value={scenarioDraft.actualMultiplier}
              />
              <TextInput
                label="Variance delta %"
                onChange={(event) =>
                  setScenarioDraft((current) => ({
                    ...current,
                    varianceDeltaPct: event.target.value,
                  }))
                }
                step="0.1"
                type="number"
                value={scenarioDraft.varianceDeltaPct}
              />
              <TextInput
                label="Win delta %"
                onChange={(event) =>
                  setScenarioDraft((current) => ({
                    ...current,
                    winProbabilityDeltaPct: event.target.value,
                  }))
                }
                step="0.1"
                type="number"
                value={scenarioDraft.winProbabilityDeltaPct}
              />
              <TextInput
                label="Schedule shift months"
                onChange={(event) =>
                  setScenarioDraft((current) => ({
                    ...current,
                    scheduleShiftMonths: event.target.value,
                  }))
                }
                step="1"
                type="number"
                value={scenarioDraft.scheduleShiftMonths}
              />
            </div>

            <InlineActionBar>
              <Button
                onClick={() => saveScenarioMutation.mutate()}
                type="button"
                variant="primary"
              >
                {saveScenarioMutation.isPending ? "Saving..." : "Save scenario assumptions"}
              </Button>
              <StatusBadge value={selectedScenario.overrunRisk.level} />
              {selectedScenario.winProbability ? (
                <StatusBadge value={selectedScenario.winProbability.probabilityBand} />
              ) : null}
            </InlineActionBar>

            <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <SummaryStat
                label="Projected total revenue"
                value={
                  selectedScenario.projectedTotalRevenue != null
                    ? formatCurrency(selectedScenario.projectedTotalRevenue, currencyCode)
                    : "Not available"
                }
              />
              <SummaryStat
                label="Weighted revenue"
                value={
                  selectedScenario.projectedWeightedRevenue != null
                    ? formatCurrency(selectedScenario.projectedWeightedRevenue, currencyCode)
                    : "Not available"
                }
              />
              <SummaryStat
                label="Scenario quote median"
                value={
                  selectedScenario.likelyQuoteRange
                    ? formatCurrency(
                        selectedScenario.likelyQuoteRange.recommendedMedian ??
                          selectedScenario.likelyQuoteRange.median,
                        currencyCode,
                      )
                    : "Not available"
                }
              />
              <SummaryStat
                label="Scenario win probability"
                value={
                  selectedScenario.winProbability
                    ? formatPercent(selectedScenario.winProbability.probabilityPct)
                    : "Not available"
                }
              />
            </div>
          </>
        ) : (
          <EmptyState
            title="No scenario available"
            description="Create or refresh a prediction run to start planning scenarios."
          />
        )}
      </SectionCard>

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <SectionCard
          title="Operator Overrides"
          description="Keep recommendations editable. These values are persisted as auditable overrides, not hidden model changes."
        >
          <div className="grid gap-4 md:grid-cols-2">
            <SelectField
              label="Quote recommendation status"
              onChange={(event) => setQuoteAcceptanceStatus(event.target.value)}
              value={quoteAcceptanceStatus}
            >
              <option value="accepted">Accepted</option>
              <option value="partial_accept">Partial accept</option>
              <option value="manual_override">Manual override</option>
            </SelectField>
            <SelectField
              label="Win probability status"
              onChange={(event) => setWinOverrideStatus(event.target.value)}
              value={winOverrideStatus}
            >
              <option value="accepted">Accepted</option>
              <option value="partial_accept">Partial accept</option>
              <option value="manual_override">Manual override</option>
            </SelectField>
            <TextInput
              label="Recommended low"
              onChange={(event) => setQuoteRecommendedLow(event.target.value)}
              step="0.01"
              type="number"
              value={quoteRecommendedLow}
            />
            <TextInput
              label="Recommended median"
              onChange={(event) => setQuoteRecommendedMedian(event.target.value)}
              step="0.01"
              type="number"
              value={quoteRecommendedMedian}
            />
            <TextInput
              label="Recommended high"
              onChange={(event) => setQuoteRecommendedHigh(event.target.value)}
              step="0.01"
              type="number"
              value={quoteRecommendedHigh}
            />
            <TextInput
              label="Manual win probability %"
              onChange={(event) => setWinProbabilityPct(event.target.value)}
              step="0.1"
              type="number"
              value={winProbabilityPct}
            />
          </div>
          <InlineActionBar>
            <Button
              onClick={() => saveOverridesMutation.mutate()}
              type="button"
              variant="primary"
            >
              {saveOverridesMutation.isPending ? "Saving..." : "Save overrides"}
            </Button>
          </InlineActionBar>
        </SectionCard>

        <SectionCard
          title="Promote To Forecast"
          description="Create a forecast draft from the selected scenario. The draft remains fully editable in the forecast editor."
        >
          <div className="grid gap-4 md:grid-cols-2">
            <TextInput
              label="Draft title"
              onChange={(event) => setPromotionTitle(event.target.value)}
              value={promotionTitle}
            />
            <TextInput
              label="Forecast probability %"
              onChange={(event) => setPromotionProbability(event.target.value)}
              step="0.1"
              type="number"
              value={promotionProbability}
            />
          </div>
          <InlineActionBar>
            <Button
              onClick={() => promoteScenarioMutation.mutate()}
              type="button"
              variant="primary"
            >
              {promoteScenarioMutation.isPending ? "Promoting..." : "Promote scenario"}
            </Button>
            <Link
              className="text-sm font-medium text-slate-700 underline-offset-4 hover:text-slate-900 hover:underline"
              href={`/projects/${projectId}/forecast`}
            >
              Open forecast editor
            </Link>
          </InlineActionBar>
        </SectionCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <SectionCard
          title="Discipline Outlook"
          description="Scenario-specific discipline value, variance, and overrun view."
        >
          {selectedScenario?.disciplineUsage?.length ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                    <th className="px-4 py-3">Discipline</th>
                    <th className="px-4 py-3">Predicted actual</th>
                    <th className="px-4 py-3">Variance</th>
                    <th className="px-4 py-3">Risk</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {selectedScenario.disciplineUsage.map((item) => (
                    <tr key={item.disciplineId}>
                      <td className="px-4 py-3">
                        <p className="font-medium text-slate-900">
                          {item.disciplineName ?? item.disciplineCode ?? item.disciplineId}
                        </p>
                        <p className="text-xs text-slate-500">{item.keyDrivers?.[0]}</p>
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {item.predictedActualAmount != null
                          ? formatCurrency(item.predictedActualAmount, currencyCode)
                          : "Not available"}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {item.predictedVariancePct != null
                          ? formatPercent(item.predictedVariancePct)
                          : "Not available"}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge value={item.overrunRisk ?? "low"} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No discipline scenario output"
              description="Refresh the prediction run to generate discipline-level scenario outputs."
            />
          )}
        </SectionCard>

        <SectionCard
          title="Monthly Revenue Spread"
          description="Scenario-specific monthly spread used when promoting a forecast draft."
        >
          {selectedScenario?.monthlyRevenueSpread?.length ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                    <th className="px-4 py-3">Month</th>
                    <th className="px-4 py-3">Median share</th>
                    <th className="px-4 py-3">Median amount</th>
                    <th className="px-4 py-3">Profile</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {selectedScenario.monthlyRevenueSpread.map((item) => (
                    <tr key={item.month}>
                      <td className="px-4 py-3 font-medium text-slate-900">{item.month}</td>
                      <td className="px-4 py-3 text-slate-700">{formatPercent(item.medianSharePct)}</td>
                      <td className="px-4 py-3 text-slate-700">
                        {item.predictedAmountMedian != null
                          ? formatCurrency(item.predictedAmountMedian, currencyCode)
                          : "Not available"}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge value={item.spreadProfile ?? "even"} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No monthly spread output"
              description="The current project still needs more schedule structure for monthly scenario planning."
            />
          )}
        </SectionCard>
      </div>
    </div>
  );
}
