"use client";

import type { ReactNode } from "react";
import { useDeferredValue, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import type { OperationalDashboardResponse } from "@quotes4/contracts";
import { useQuery } from "@tanstack/react-query";

import { getBrowserApiClient } from "@/lib/api/browser-client";
import { formatCurrency, formatDateTime, formatPercent } from "@/lib/format";
import { queryKeys } from "@/lib/query/keys";

import { SelectField } from "@/components/forms/select-field";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { SummaryStat } from "@/components/ui/summary-stat";

import {
  AwardedLostChart,
  BenchmarkBandList,
  ConfidenceBandCards,
  DisciplineStackedChart,
  PipelineChart,
  RevenueLineChart,
  VarianceDivergingChart,
} from "./dashboard-charts";
import { DrilldownDrawer } from "./drilldown-drawer";
import { ForecastRevenueWorkspace as ForecastRevenueReport } from "./forecast-revenue-workspace";
import {
  buildDisciplineRevenueTrendsFromDataset,
  buildForecastRevenueFromDataset,
  buildMonthlyRevenueForecastFromDataset,
  type DashboardFilters,
  type DashboardView,
  formatDashboardMonth,
  getDashboardViewForSummaryCard,
  getDefaultDashboardFilters,
  parseDashboardFilters,
  serializeDashboardFilters,
  toDashboardQueryOptions,
} from "./dashboard-helpers";
import { ProjectBenchmarkPanel } from "./project-benchmark-panel";

function DashboardPanel({
  actionLabel = "Open detail",
  children,
  description,
  onOpen,
  testId,
  title,
}: {
  actionLabel?: string;
  children: ReactNode;
  description: string;
  onOpen: () => void;
  testId: string;
  title: string;
}) {
  return (
    <SectionCard
      actions={
        <Button
          data-testid={testId}
          onClick={onOpen}
          type="button"
          variant="secondary"
        >
          {actionLabel}
        </Button>
      }
      description={description}
      title={title}
    >
      {children}
    </SectionCard>
  );
}

function DashboardFiltersBar({
  filters,
  isPending,
  onFilterChange,
  onReset,
  options,
}: {
  filters: DashboardFilters;
  isPending: boolean;
  onFilterChange: (
    key: keyof DashboardFilters,
    value: string | undefined,
  ) => void;
  onReset: () => void;
  options: OperationalDashboardResponse["filterOptions"] | undefined;
}) {
  return (
    <section className="sticky top-0 z-20 rounded-xl border border-slate-200 bg-white/95 px-4 py-4 shadow-sm backdrop-blur">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div className="grid flex-1 gap-3 md:grid-cols-2 xl:grid-cols-7">
          <label className="grid gap-1.5">
            <span className="text-sm font-medium text-slate-700">From month</span>
            <input
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
              data-testid="dashboard-filter-fromMonth"
              onChange={(event) =>
                onFilterChange("fromMonth", event.currentTarget.value)
              }
              type="month"
              value={filters.fromMonth}
            />
          </label>

          <label className="grid gap-1.5">
            <span className="text-sm font-medium text-slate-700">To month</span>
            <input
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
              data-testid="dashboard-filter-toMonth"
              onChange={(event) =>
                onFilterChange("toMonth", event.currentTarget.value)
              }
              type="month"
              value={filters.toMonth}
            />
          </label>

          <SelectField
            data-testid="dashboard-filter-clientId"
            label="Client"
            onChange={(event) =>
              onFilterChange(
                "clientId",
                event.currentTarget.value || undefined,
              )
            }
            value={filters.clientId ?? ""}
          >
            <option value="">All clients</option>
            {(options?.clients ?? []).map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </SelectField>

          <SelectField
            data-testid="dashboard-filter-projectId"
            label="Project"
            onChange={(event) =>
              onFilterChange(
                "projectId",
                event.currentTarget.value || undefined,
              )
            }
            value={filters.projectId ?? ""}
          >
            <option value="">All projects</option>
            {(options?.projects ?? []).map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </SelectField>

          <SelectField
            data-testid="dashboard-filter-disciplineId"
            label="Discipline"
            onChange={(event) =>
              onFilterChange(
                "disciplineId",
                event.currentTarget.value || undefined,
              )
            }
            value={filters.disciplineId ?? ""}
          >
            <option value="">All disciplines</option>
            {(options?.disciplines ?? []).map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </SelectField>

          <SelectField
            data-testid="dashboard-filter-status"
            label="Status"
            onChange={(event) =>
              onFilterChange("status", event.currentTarget.value || undefined)
            }
            value={filters.status ?? ""}
          >
            <option value="">All statuses</option>
            {(options?.statuses ?? []).map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
              ))}
          </SelectField>

          <SelectField
            data-testid="dashboard-filter-scenarioKey"
            label="Scenario"
            onChange={(event) =>
              onFilterChange(
                "scenarioKey",
                event.currentTarget.value || undefined,
              )
            }
            value={filters.scenarioKey ?? "base"}
          >
            {(options?.scenarios ?? []).map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </SelectField>
        </div>

        <div className="flex items-center gap-2">
          <Button
            data-testid="dashboard-reset-filters"
            onClick={onReset}
            type="button"
            variant="ghost"
          >
            Reset filters
          </Button>
          <div className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
            {isPending ? "Refreshing…" : "Live aggregates"}
          </div>
        </div>
      </div>
    </section>
  );
}

export function OperationalDashboardPage() {
  const api = getBrowserApiClient();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [openView, setOpenView] = useState<DashboardView | null>(null);

  const filterSearch = searchParams.toString();
  const deferredFilterSearch = useDeferredValue(filterSearch);
  const filters = parseDashboardFilters(filterSearch);
  const queryFilters = parseDashboardFilters(deferredFilterSearch);
  const filtersKey = serializeDashboardFilters(queryFilters);

  const dashboardQuery = useQuery({
    placeholderData: (previousData) => previousData,
    queryFn: async () => api.getOperationalDashboard(toDashboardQueryOptions(queryFilters)),
    queryKey: queryKeys.operationalDashboard(filtersKey),
  });

  const dashboard = dashboardQuery.data ?? null;
  const forecastRevenueView = dashboard
    ? buildForecastRevenueFromDataset(dashboard.forecastDataset)
    : null;
  const monthlyRevenueForecastView = dashboard
    ? buildMonthlyRevenueForecastFromDataset(dashboard.forecastDataset)
    : null;
  const disciplineRevenueTrendsView = dashboard
    ? buildDisciplineRevenueTrendsFromDataset(dashboard.forecastDataset)
    : null;
  const filterOptions = dashboard?.filterOptions;
  const selectedProjectLabel =
    filterOptions?.projects.find((item) => item.id === filters.projectId)?.label ??
    filters.projectId;

  function updateFilters(nextFilters: DashboardFilters) {
    const nextSearch = serializeDashboardFilters(nextFilters);

    startTransition(() => {
      router.replace(`${pathname}?${nextSearch}`, { scroll: false });
    });
  }

  function handleFilterChange(
    key: keyof DashboardFilters,
    rawValue: string | undefined,
  ) {
    const value = rawValue || undefined;
    const nextFilters: DashboardFilters = {
      ...filters,
      [key]: value,
    };

    if (key === "clientId") {
      nextFilters.projectId = undefined;
    }

    if (key === "fromMonth" && value && value > nextFilters.toMonth) {
      nextFilters.toMonth = value;
    }

    if (key === "toMonth" && value && value < nextFilters.fromMonth) {
      nextFilters.fromMonth = value;
    }

    updateFilters(nextFilters);
  }

  function handleResetFilters() {
    updateFilters({
      ...getDefaultDashboardFilters(),
      clientId: undefined,
      projectId: undefined,
      disciplineId: undefined,
      status: undefined,
      scenarioKey: "base",
    });
  }

  function openPanel(view: DashboardView) {
    setOpenView(view);
  }

  return (
    <div className="space-y-6">
      <DashboardFiltersBar
        filters={filters}
        isPending={isPending || dashboardQuery.isFetching}
        onFilterChange={handleFilterChange}
        onReset={handleResetFilters}
        options={filterOptions}
      />

      {dashboard ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          <p>
            Showing {formatDashboardMonth(filters.fromMonth)} to{" "}
            {formatDashboardMonth(filters.toMonth)}
            {filters.clientId ? ` · Client filter applied` : ""}
            {filters.projectId ? ` · Project filter applied` : ""}
            {filters.disciplineId ? ` · Discipline filter applied` : ""}
            {filters.status ? ` · Status ${filters.status}` : ""}
            {filters.scenarioKey ? ` · Scenario ${filters.scenarioKey}` : ""}
          </p>
          <p>Updated {formatDateTime(dashboard.generatedAt)}</p>
        </div>
      ) : null}

      {dashboardQuery.error && !dashboard ? (
        <ErrorState
          title="Dashboard unavailable"
          description="The operational dashboard could not be loaded from the API."
        />
      ) : null}

      {!dashboard && dashboardQuery.isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div
              className="h-28 animate-pulse rounded-xl border border-slate-200 bg-slate-100"
              key={index}
            />
          ))}
        </div>
      ) : null}

      {dashboard ? (
        <>
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {dashboard.summaryCards.map((card) => {
              const view = getDashboardViewForSummaryCard(card.key);

              if (!view) {
                return (
                  <SummaryStat
                    hint={card.detail}
                    key={card.key}
                    label={card.label}
                    value={card.value}
                  />
                );
              }

              return (
                <button
                  className="block w-full text-left"
                  data-testid={`dashboard-summary-${card.key}`}
                  key={card.key}
                  onClick={() => openPanel(view)}
                  type="button"
                >
                  <SummaryStat
                    hint={`${card.detail} · Open detail`}
                    label={card.label}
                    value={card.value}
                  />
                </button>
              );
            })}
          </section>

          <SectionCard
            actions={
              <Button
                data-testid="dashboard-open-forecast-revenue-drilldown"
                onClick={() => openPanel("monthly_forecast")}
                type="button"
                variant="secondary"
              >
                Open drilldown
              </Button>
            }
            description="Read-only month-by-month revenue reporting by status and project. Use Revenue Phasing for spreadsheet-style month edits and manual overrides."
            title="Forecast Revenue Report"
          >
            {forecastRevenueView ? (
              <ForecastRevenueReport forecastRevenue={forecastRevenueView} />
            ) : null}
          </SectionCard>

          <section className="grid gap-6 xl:grid-cols-2">
            <DashboardPanel
              description="Quote totals by status, with weighted value called out inside each stage."
              onOpen={() => openPanel("sales_pipeline")}
              testId="dashboard-open-sales_pipeline"
              title="Sales Pipeline"
            >
              <div className="grid gap-4 border-b border-slate-200 pb-4 md:grid-cols-3">
                <SummaryStat
                  label="Total quote amount"
                  value={formatCurrency(
                    dashboard.salesPipeline.totalQuoteAmount,
                    dashboard.salesPipeline.currencyCode,
                  )}
                />
                <SummaryStat
                  label="Total weighted amount"
                  value={formatCurrency(
                    dashboard.salesPipeline.totalWeightedAmount,
                    dashboard.salesPipeline.currencyCode,
                  )}
                />
                <SummaryStat
                  label="Booked operational amount"
                  value={formatCurrency(
                    dashboard.salesPipeline.totalBookedAmount,
                    dashboard.salesPipeline.currencyCode,
                  )}
                />
              </div>
              <div
                className="mt-4"
                role="button"
                tabIndex={0}
                onClick={() => openPanel("sales_pipeline")}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openPanel("sales_pipeline");
                  }
                }}
              >
                <PipelineChart
                  currencyCode={dashboard.salesPipeline.currencyCode}
                  stages={dashboard.salesPipeline.stages}
                />
              </div>
            </DashboardPanel>

            <DashboardPanel
              description="Unified forecast totals across the active month window."
              onOpen={() => openPanel("monthly_forecast")}
              testId="dashboard-open-monthly_forecast"
              title="Monthly Revenue Forecast"
            >
              {monthlyRevenueForecastView && monthlyRevenueForecastView.months.length > 0 ? (
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => openPanel("monthly_forecast")}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      openPanel("monthly_forecast");
                    }
                  }}
                >
                  <RevenueLineChart
                    currencyCode={monthlyRevenueForecastView.currencyCode}
                    months={monthlyRevenueForecastView.months}
                  />
                </div>
              ) : (
                <EmptyState
                  title="No forecast months in range"
                  description="Adjust the month window or clear project-level filters to widen the forecast view."
                />
              )}
            </DashboardPanel>

            <DashboardPanel
              description="Awarded and lost outcomes by month, with volume called out beside each bar group."
              onOpen={() => openPanel("awarded_lost")}
              testId="dashboard-open-awarded_lost"
              title="Awarded vs Lost Trend"
            >
              {dashboard.awardedLostTrend.months.length > 0 ? (
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => openPanel("awarded_lost")}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      openPanel("awarded_lost");
                    }
                  }}
                >
                  <AwardedLostChart
                    currencyCode={dashboard.awardedLostTrend.currencyCode}
                    months={dashboard.awardedLostTrend.months}
                  />
                </div>
              ) : (
                <EmptyState
                  title="No awarded or lost outcomes in range"
                  description="This trend fills once awarded or lost project outcomes fall inside the selected month window."
                />
              )}
            </DashboardPanel>

            <DashboardPanel
              description="Variance buckets show where quoted work finished under, on, or over plan."
              onOpen={() => openPanel("variance")}
              testId="dashboard-open-variance"
              title="Quote vs Actual Variance"
            >
              <div className="grid gap-4 border-b border-slate-200 pb-4 md:grid-cols-2">
                <SummaryStat
                  label="Complete actuals"
                  value={dashboard.quoteActualVariance.completeActualsCount}
                  hint={`${dashboard.quoteActualVariance.projectCount} benchmarked projects`}
                />
                <SummaryStat
                  label="Median variance"
                  tone={
                    dashboard.quoteActualVariance.medianVariancePct != null &&
                    Math.abs(dashboard.quoteActualVariance.medianVariancePct) > 10
                      ? "warning"
                      : "default"
                  }
                  value={
                    dashboard.quoteActualVariance.medianVariancePct == null
                      ? "N/A"
                      : formatPercent(
                          dashboard.quoteActualVariance.medianVariancePct,
                        )
                  }
                />
              </div>
              <div
                className="mt-4"
                role="button"
                tabIndex={0}
                onClick={() => openPanel("variance")}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openPanel("variance");
                  }
                }}
              >
                <VarianceDivergingChart
                  buckets={dashboard.quoteActualVariance.buckets}
                  currencyCode={dashboard.quoteActualVariance.currencyCode}
                />
              </div>
            </DashboardPanel>

            <DashboardPanel
              description="Top clients by quoted volume, with win/loss context and benchmark variance."
              onOpen={() => openPanel("client_history")}
              testId="dashboard-open-client_history"
              title="Client / Project History Summary"
            >
              {dashboard.clientProjectHistory.clients.length > 0 ? (
                <div
                  className="overflow-x-auto"
                  role="button"
                  tabIndex={0}
                  onClick={() => openPanel("client_history")}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      openPanel("client_history");
                    }
                  }}
                >
                  <table className="min-w-full border-separate border-spacing-0 text-sm">
                    <thead>
                      <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                        <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
                          Client
                        </th>
                        <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
                          Projects
                        </th>
                        <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
                          Awarded / Lost
                        </th>
                        <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
                          Quoted
                        </th>
                        <th className="border-b border-slate-200 pb-2 font-medium">
                          Median variance
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {dashboard.clientProjectHistory.clients
                        .slice()
                        .sort(
                          (left, right) => right.quotedAmount - left.quotedAmount,
                        )
                        .slice(0, 6)
                        .map((client) => (
                          <tr key={client.clientId}>
                            <td className="border-b border-slate-100 py-3 pr-4 font-medium text-slate-900">
                              {client.clientName}
                            </td>
                            <td className="border-b border-slate-100 py-3 pr-4 text-slate-700">
                              {client.projectCount}
                            </td>
                            <td className="border-b border-slate-100 py-3 pr-4 text-slate-700">
                              {client.awardedCount} / {client.lostCount}
                            </td>
                            <td className="border-b border-slate-100 py-3 pr-4 text-slate-700">
                              {formatCurrency(
                                client.quotedAmount,
                                dashboard.clientProjectHistory.currencyCode,
                              )}
                            </td>
                            <td className="border-b border-slate-100 py-3 text-slate-700">
                              {client.medianVariancePct == null
                                ? "N/A"
                                : formatPercent(client.medianVariancePct)}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState
                  title="No client history available"
                  description="Client history populates once quoted and benchmarked work exists inside the selected filter set."
                />
              )}
            </DashboardPanel>

            <DashboardPanel
              description="Monthly forecast totals by discipline, stacked so the workload mix stays visible at a glance."
              onOpen={() => openPanel("discipline_trends")}
              testId="dashboard-open-discipline_trends"
              title="Discipline Revenue Trends"
            >
              {disciplineRevenueTrendsView && disciplineRevenueTrendsView.months.length > 0 ? (
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => openPanel("discipline_trends")}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      openPanel("discipline_trends");
                    }
                  }}
                >
                  <DisciplineStackedChart
                    currencyCode={disciplineRevenueTrendsView.currencyCode}
                    months={disciplineRevenueTrendsView.months}
                    series={disciplineRevenueTrendsView.series}
                  />
                </div>
              ) : (
                <EmptyState
                  title="No discipline forecast in range"
                  description="Clear narrow filters or widen the month window to inspect discipline revenue mix."
                />
              )}
            </DashboardPanel>

            <DashboardPanel
              description="Confidence stays explainable: one score, three bands, and clear scoring rules."
              onOpen={() => openPanel("forecast_confidence")}
              testId="dashboard-open-forecast_confidence"
              title="Forecast Confidence View"
            >
              <div
                role="button"
                tabIndex={0}
                onClick={() => openPanel("forecast_confidence")}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openPanel("forecast_confidence");
                  }
                }}
              >
                <ConfidenceBandCards
                  averageScore={dashboard.forecastConfidence.averageScore}
                  bands={dashboard.forecastConfidence.bands}
                  highConfidenceCount={
                    dashboard.forecastConfidence.highConfidenceProjectCount
                  }
                  projectCount={dashboard.forecastConfidence.projectCount}
                />
              </div>
              <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                <p className="font-medium text-slate-900">Scoring bands</p>
                <p className="mt-2">
                  High is 75 or above. Medium is 50 to 74. Low is below 50.
                  Open the drilldown to rank projects and inspect the raw score
                  inputs.
                </p>
              </div>
            </DashboardPanel>

            <DashboardPanel
              description="Cross-project benchmark coverage, variance bands, and discipline-level benchmark medians."
              onOpen={() => openPanel("benchmark_overview")}
              testId="dashboard-open-benchmark_overview"
              title="Comparable Project Benchmarks"
            >
              <div className="grid gap-4 border-b border-slate-200 pb-4 md:grid-cols-3">
                <SummaryStat
                  label="Benchmarked projects"
                  value={dashboard.benchmarkOverview.benchmarkProjectCount}
                />
                <SummaryStat
                  label="Complete actuals"
                  value={dashboard.benchmarkOverview.completeActualsCount}
                />
                <SummaryStat
                  label="Median variance"
                  value={
                    dashboard.benchmarkOverview.medianVariancePct == null
                      ? "N/A"
                      : formatPercent(
                          dashboard.benchmarkOverview.medianVariancePct,
                        )
                  }
                />
              </div>
              <div
                className="mt-4 space-y-4"
                role="button"
                tabIndex={0}
                onClick={() => openPanel("benchmark_overview")}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openPanel("benchmark_overview");
                  }
                }}
              >
                <BenchmarkBandList
                  buckets={dashboard.benchmarkOverview.varianceBands}
                  currencyCode={dashboard.benchmarkOverview.currencyCode}
                />
                {dashboard.benchmarkOverview.disciplines.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-separate border-spacing-0 text-sm">
                      <thead>
                        <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                          <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
                            Discipline
                          </th>
                          <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
                            Projects
                          </th>
                          <th className="border-b border-slate-200 pb-2 font-medium">
                            Median variance
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {dashboard.benchmarkOverview.disciplines.map((item) => (
                          <tr key={item.disciplineId}>
                            <td className="border-b border-slate-100 py-3 pr-4 font-medium text-slate-900">
                              {item.disciplineName}
                            </td>
                            <td className="border-b border-slate-100 py-3 pr-4 text-slate-700">
                              {item.projectCount}
                            </td>
                            <td className="border-b border-slate-100 py-3 text-slate-700">
                              {item.medianVariancePct == null
                                ? "N/A"
                                : formatPercent(item.medianVariancePct)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState
                    title="No discipline benchmarks"
                    description="Discipline medians appear when complete benchmark actuals exist for the current filter set."
                  />
                )}
              </div>
            </DashboardPanel>
          </section>

          <ProjectBenchmarkPanel
            projectId={filters.projectId}
            projectLabel={selectedProjectLabel}
          />
        </>
      ) : null}

      <DrilldownDrawer
        filters={filters}
        onClose={() => setOpenView(null)}
        view={openView}
      />
    </div>
  );
}
