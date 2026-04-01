import type {
  DashboardDrilldownColumn,
  DashboardQueryOptions,
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
