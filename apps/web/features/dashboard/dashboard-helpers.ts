import type {
  DashboardDrilldownColumn,
  DashboardQueryOptions,
  OperationalDashboardResponse,
} from "@quotes4/contracts";

import {
  formatCurrency,
  formatDate,
  formatPercent,
  formatStatusLabel,
} from "../../lib/format";

export type DashboardView =
  | "sales_pipeline"
  | "monthly_forecast"
  | "awarded_lost"
  | "variance"
  | "client_history"
  | "discipline_trends"
  | "forecast_confidence"
  | "benchmark_overview";

export interface DashboardFilters {
  fromMonth: string;
  toMonth: string;
  clientId: string | undefined;
  projectId: string | undefined;
  disciplineId: string | undefined;
  status: string | undefined;
  scenarioKey: string | undefined;
}

const FILTER_ORDER: Array<keyof DashboardFilters> = [
  "fromMonth",
  "toMonth",
  "clientId",
  "projectId",
  "disciplineId",
  "status",
  "scenarioKey",
];

const SUMMARY_CARD_VIEW_MAP: Record<string, DashboardView> = {
  open_pipeline: "sales_pipeline",
  weighted_forecast: "monthly_forecast",
  booked_forecast: "monthly_forecast",
  awarded_projects: "awarded_lost",
  lost_projects: "awarded_lost",
  benchmark_median_variance: "benchmark_overview",
  high_confidence: "forecast_confidence",
};

function isMonthValue(value: string | null | undefined): value is string {
  return typeof value === "string" && /^\d{4}-\d{2}$/.test(value);
}

function normalizeOptionalValue(value: string | null): string | undefined {
  if (!value) {
    return undefined;
  }

  return value;
}

function shiftMonth(referenceDate: Date, delta: number): string {
  const value = new Date(
    Date.UTC(referenceDate.getUTCFullYear(), referenceDate.getUTCMonth(), 1),
  );
  value.setUTCMonth(value.getUTCMonth() + delta);

  return [
    value.getUTCFullYear().toString().padStart(4, "0"),
    (value.getUTCMonth() + 1).toString().padStart(2, "0"),
  ].join("-");
}

function getSearchParams(
  source: string | URLSearchParams | { toString(): string },
): URLSearchParams {
  if (typeof source === "string") {
    return new URLSearchParams(source);
  }

  if (source instanceof URLSearchParams) {
    return new URLSearchParams(source);
  }

  return new URLSearchParams(source.toString());
}

export function getDefaultDashboardFilters(referenceDate = new Date()) {
  return {
    fromMonth: shiftMonth(referenceDate, -5),
    toMonth: shiftMonth(referenceDate, 6),
    scenarioKey: "base",
  };
}

export function parseDashboardFilters(
  source: string | URLSearchParams | { toString(): string },
  referenceDate = new Date(),
): DashboardFilters {
  const params = getSearchParams(source);
  const defaults = getDefaultDashboardFilters(referenceDate);
  const fromMonth = isMonthValue(params.get("fromMonth"))
    ? (params.get("fromMonth") as string)
    : defaults.fromMonth;
  const toMonth = isMonthValue(params.get("toMonth"))
    ? (params.get("toMonth") as string)
    : defaults.toMonth;

  return {
    fromMonth,
    toMonth,
    clientId: normalizeOptionalValue(params.get("clientId")),
    projectId: normalizeOptionalValue(params.get("projectId")),
    disciplineId: normalizeOptionalValue(params.get("disciplineId")),
    status: normalizeOptionalValue(params.get("status")),
    scenarioKey: normalizeOptionalValue(params.get("scenarioKey")) ?? defaults.scenarioKey,
  };
}

export function serializeDashboardFilters(filters: DashboardFilters): string {
  const params = new URLSearchParams();

  FILTER_ORDER.forEach((key) => {
    const value = filters[key];
    if (!value) {
      return;
    }

    params.set(key, value);
  });

  return params.toString();
}

export function toDashboardQueryOptions(
  filters: DashboardFilters,
): DashboardQueryOptions {
  return {
    fromMonth: filters.fromMonth,
    toMonth: filters.toMonth,
    ...(filters.clientId ? { clientId: filters.clientId } : {}),
    ...(filters.projectId ? { projectId: filters.projectId } : {}),
    ...(filters.disciplineId ? { disciplineId: filters.disciplineId } : {}),
    ...(filters.status ? { status: filters.status } : {}),
    ...(filters.scenarioKey ? { scenarioKey: filters.scenarioKey } : {}),
  };
}

export function getConfidenceBandLabel(band: string): string {
  if (band === "high" || band === "medium" || band === "low") {
    return band.charAt(0).toUpperCase() + band.slice(1);
  }

  return band;
}

export function getDashboardViewForSummaryCard(key: string): DashboardView | null {
  return SUMMARY_CARD_VIEW_MAP[key] ?? null;
}

export function formatDashboardMonth(month: string): string {
  if (!isMonthValue(month)) {
    return month;
  }

  const [year, value] = month.split("-");
  return new Intl.DateTimeFormat("en-GB", {
    month: "short",
    year: "2-digit",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(Number(year), Number(value) - 1, 1)));
}

export function formatDrilldownValue(
  column: DashboardDrilldownColumn,
  value: string | number | null | undefined,
  currencyCode = "GBP",
): string {
  if (value == null) {
    return "—";
  }

  if (column.kind === "currency" && typeof value === "number") {
    return formatCurrency(value, currencyCode);
  }

  if (column.kind === "percent" && typeof value === "number") {
    return formatPercent(value);
  }

  if (column.kind === "number" && typeof value === "number") {
    return new Intl.NumberFormat("en-GB", {
      maximumFractionDigits: Number.isInteger(value) ? 0 : 2,
    }).format(value);
  }

  if (column.kind === "date" && typeof value === "string") {
    return formatDate(value);
  }

  if (column.kind === "month" && typeof value === "string") {
    return formatDashboardMonth(value);
  }

  if (column.kind === "status" && typeof value === "string") {
    return formatStatusLabel(value);
  }

  return String(value);
}

export function formatDrilldownTotalLabel(key: string): string {
  const labels: Record<string, string> = {
    projectCount: "Projects",
    clientCount: "Clients",
    eventCount: "Events",
    quoteTotal: "Quote Total",
    quotedAmount: "Quoted Amount",
    grossAmount: "Gross Amount",
    weightedAmount: "Weighted Amount",
    actualAmount: "Actual Amount",
    weightedValue: "Weighted Value",
    varianceAmount: "Variance",
    averageScore: "Average Score",
  };

  return labels[key] ?? formatStatusLabel(key);
}

export function getDashboardCsvFileName(
  view: DashboardView,
  filters: DashboardFilters,
): string {
  return `quotes4-${view}-${filters.fromMonth}-to-${filters.toMonth}.csv`;
}

function formatDatasetDisciplineLabel(value: string | null): string {
  if (!value) {
    return "Unassigned";
  }

  return value
    .split("_")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function mapDatasetStatusToLegacyStatus(
  status: OperationalDashboardResponse["forecastDataset"]["projects"][number]["status"],
): "bid" | "awarded" | "lost" {
  if (status === "estimated") {
    return "bid";
  }

  return status;
}

function summarizeMethods(methods: string[]): string {
  const unique = Array.from(new Set(methods.filter(Boolean)));
  if (unique.length === 0) {
    return "none";
  }
  if (unique.length === 1) {
    return unique[0] as string;
  }
  return "mixed";
}

export function buildMonthlyRevenueForecastFromDataset(
  dataset: OperationalDashboardResponse["forecastDataset"],
): OperationalDashboardResponse["monthlyRevenueForecast"] {
  return {
    currencyCode: dataset.currencyCode,
    months: dataset.aggregations.totalsByMonth.map((item) => ({
      month: item.month,
      grossAmount: item.revenueValue,
      weightedAmount: 0,
      lowAmount: null,
      highAmount: null,
      actualAmount: null,
      bookedAmount: null,
    })),
  };
}

export function buildDisciplineRevenueTrendsFromDataset(
  dataset: OperationalDashboardResponse["forecastDataset"],
): OperationalDashboardResponse["disciplineRevenueTrends"] {
  const monthKeys = dataset.aggregations.totalsByMonth.map((item) => item.month);
  const grouped: Record<string, Record<string, number>> = {};

  dataset.monthlyRows.forEach((row) => {
    const disciplineKey = row.discipline ?? "__unassigned__";
    grouped[disciplineKey] ??= {};
    grouped[disciplineKey]![row.month] = (grouped[disciplineKey]![row.month] ?? 0) + row.revenueValue;
  });

  return {
    currencyCode: dataset.currencyCode,
    months: monthKeys,
    series: Object.entries(grouped)
      .sort(([leftKey], [rightKey]) => leftKey.localeCompare(rightKey))
      .map(([disciplineKey, monthValues]) => ({
        disciplineId: disciplineKey === "__unassigned__" ? "unassigned" : disciplineKey,
        disciplineName:
          disciplineKey === "__unassigned__"
            ? "Unassigned"
            : formatDatasetDisciplineLabel(disciplineKey),
        points: monthKeys.map((month) => ({
          month,
          grossAmount: monthValues[month] ?? 0,
          weightedAmount: 0,
        })),
      })),
  };
}

export function buildForecastRevenueFromDataset(
  dataset: OperationalDashboardResponse["forecastDataset"],
): OperationalDashboardResponse["forecastRevenue"] {
  const monthKeys = dataset.aggregations.totalsByMonth.map((item) => item.month);
  const projectById = Object.fromEntries(
    dataset.projects.map((project) => [project.projectId, project]),
  );
  const rowsByProject = new Map<
    string,
    OperationalDashboardResponse["forecastDataset"]["monthlyRows"]
  >();

  dataset.monthlyRows.forEach((row) => {
    const existing = rowsByProject.get(row.projectId) ?? [];
    existing.push(row);
    rowsByProject.set(row.projectId, existing);
  });

  const monthlyStatusTotals = monthKeys.map((month) => {
    const estimatedAmount = dataset.monthlyRows
      .filter((row) => row.month === month && projectById[row.projectId]?.status === "estimated")
      .reduce((sum, row) => sum + row.revenueValue, 0);
    const awardedAmount = dataset.monthlyRows
      .filter((row) => row.month === month && projectById[row.projectId]?.status === "awarded")
      .reduce((sum, row) => sum + row.revenueValue, 0);
    const lostAmount = dataset.monthlyRows
      .filter((row) => row.month === month && projectById[row.projectId]?.status === "lost")
      .reduce((sum, row) => sum + row.revenueValue, 0);

    return {
      month,
      bidAmount: estimatedAmount,
      weightedBidAmount: 0,
      awardedAmount,
      activeAmount: 0,
      completeAmount: 0,
      bookedAmount: awardedAmount,
      lostAmount,
    };
  });

  const overallStatusTotals = dataset.aggregations.totalsByStatus.map((item) => ({
    status: mapDatasetStatusToLegacyStatus(item.status),
    label: formatStatusLabel(mapDatasetStatusToLegacyStatus(item.status)),
    projectCount: dataset.projects.filter((project) => project.status === item.status).length,
    totalAmount: item.revenueValue,
    weightedTotalAmount: 0,
  }));

  const projectRows = dataset.projects.map((project) => {
    const projectMonthlyRows = rowsByProject.get(project.projectId) ?? [];
    const monthValues = monthKeys.map((month) => {
      const amount = projectMonthlyRows
        .filter((row) => row.month === month)
        .reduce((sum, row) => sum + row.revenueValue, 0);

      return {
        month,
        amount,
        weightedAmount: 0,
        actualAmount: 0,
        bookedAmount: project.status === "awarded" ? amount : 0,
      };
    });
    const disciplineGroups = new Map<
      string,
      OperationalDashboardResponse["forecastDataset"]["monthlyRows"]
    >();

    projectMonthlyRows.forEach((row) => {
      const disciplineKey = row.discipline ?? "__unassigned__";
      const existing = disciplineGroups.get(disciplineKey) ?? [];
      existing.push(row);
      disciplineGroups.set(disciplineKey, existing);
    });
    const disciplineRows = Array.from(disciplineGroups.entries())
      .map(([disciplineKey, detailRows]) => {
        const detailMonthValues = Object.fromEntries(
          monthKeys.map((month) => [
            month,
            detailRows
              .filter((row) => row.month === month)
              .reduce((sum, row) => sum + row.revenueValue, 0),
          ]),
        );

        return {
          disciplineId: disciplineKey === "__unassigned__" ? "unassigned" : disciplineKey,
          disciplineName:
            disciplineKey === "__unassigned__"
              ? "Unassigned"
              : formatDatasetDisciplineLabel(disciplineKey),
          basePhasingProfile: "contract_dataset",
          forecastMethod: summarizeMethods(detailRows.map((row) => row.allocationMethod)),
          lineCount: detailRows.length,
          manualOverrideLineCount: detailRows.filter((row) => row.overrideFlag).length,
          totalAmount: detailRows.reduce((sum, row) => sum + row.revenueValue, 0),
          weightedTotalAmount: 0,
          monthValues: monthKeys.map((month) => ({
            month,
            amount: detailMonthValues[month] ?? 0,
            weightedAmount: 0,
            actualAmount: 0,
            bookedAmount:
              project.status === "awarded"
                ? detailMonthValues[month] ?? 0
                : 0,
          })),
        };
      })
      .sort((left, right) => right.totalAmount - left.totalAmount);

    return {
      projectId: project.projectId,
      projectName: project.projectName,
      clientId: project.projectId,
      clientName: project.client,
      status: mapDatasetStatusToLegacyStatus(project.status),
      quoteEntryDate: null,
      executionStartDate: project.executionStartDate ?? null,
      executionEndDate: project.executionEndDate ?? null,
      quoteToExecutionLeadMonths: null,
      spanningMonthCount: monthValues.filter((item) => item.amount > 0).length,
      basePhasingProfile: "contract_dataset",
      forecastMethod: summarizeMethods(projectMonthlyRows.map((row) => row.allocationMethod)),
      manualOverrideLineCount: projectMonthlyRows.filter((row) => row.overrideFlag).length,
      totalRevenue: project.totalForecastValue,
      windowRevenue: project.totalForecastValue,
      weightedTotalRevenue: 0,
      windowWeightedRevenue: 0,
      forecastVersionId: null,
      forecastStatus: null,
      scenarioKey: dataset.scenarioKey,
      changeSummary: null,
      explanationSummary: null,
      monthValues,
      disciplineRows,
    };
  });

  return {
    currencyCode: dataset.currencyCode,
    months: monthKeys,
    monthlyStatusTotals,
    overallStatusTotals,
    projectRows,
  };
}
