"use client";

import Link from "next/link";
import { Fragment, useState } from "react";

import type { OperationalDashboardResponse } from "@quotes4/contracts";

import { formatCurrency, formatDate, formatStatusLabel } from "@/lib/format";

import { EmptyState } from "@/components/ui/empty-state";
import { SummaryStat } from "@/components/ui/summary-stat";

import { formatDashboardMonth } from "./dashboard-helpers";

type ForecastRevenueSection = OperationalDashboardResponse["forecastRevenue"];
type ForecastRevenueProjectRow = ForecastRevenueSection["projectRows"][number];
type SortKey =
  | "projectName"
  | "clientName"
  | "status"
  | "executionStartDate"
  | "quoteToExecutionLeadMonths"
  | "totalRevenue"
  | "windowRevenue";

const compactCurrencyFormatter = new Intl.NumberFormat("en-GB", {
  currency: "GBP",
  maximumFractionDigits: 1,
  notation: "compact",
  style: "currency",
});

function getMaxValue(values: number[]): number {
  return Math.max(...values, 1);
}

function getCoordinates(
  values: number[],
  width: number,
  height: number,
  paddingX: number,
  paddingY: number,
) {
  const maxValue = getMaxValue(values);
  const usableWidth = width - paddingX * 2;
  const usableHeight = height - paddingY * 2;

  return values.map((value, index) => {
    const x =
      values.length === 1
        ? width / 2
        : paddingX + (usableWidth / (values.length - 1)) * index;
    const y = height - paddingY - (value / maxValue) * usableHeight;
    return { x, y };
  });
}

function getLinePoints(
  values: number[],
  width: number,
  height: number,
  paddingX: number,
  paddingY: number,
) {
  return getCoordinates(values, width, height, paddingX, paddingY)
    .map((point) => `${point.x},${point.y}`)
    .join(" ");
}

function formatMatrixCurrency(amount: number, currencyCode: string): string {
  if (Math.abs(amount) < 0.005) {
    return "—";
  }

  if (currencyCode === "GBP") {
    return compactCurrencyFormatter.format(amount);
  }

  return formatCurrency(amount, currencyCode);
}

function compareNullableString(left: string | null | undefined, right: string | null | undefined) {
  if (!left && !right) {
    return 0;
  }
  if (!left) {
    return 1;
  }
  if (!right) {
    return -1;
  }
  return left.localeCompare(right);
}

function compareNullableNumber(left: number | null | undefined, right: number | null | undefined) {
  if (left == null && right == null) {
    return 0;
  }
  if (left == null) {
    return 1;
  }
  if (right == null) {
    return -1;
  }
  return left - right;
}

function getDefaultDirection(sortKey: SortKey): "asc" | "desc" {
  if (sortKey === "totalRevenue" || sortKey === "windowRevenue") {
    return "desc";
  }
  return "asc";
}

function getStatusToneClass(status: string): string {
  const byStatus: Record<string, string> = {
    bid: "bg-amber-100 text-amber-900",
    awarded: "bg-emerald-100 text-emerald-900",
    active: "bg-sky-100 text-sky-900",
    complete: "bg-slate-200 text-slate-900",
    lost: "bg-rose-100 text-rose-900",
  };

  return byStatus[status] ?? "bg-slate-100 text-slate-900";
}

function formatLeadMonths(value: number | null | undefined): string {
  if (value == null) {
    return "—";
  }
  if (value === 0) {
    return "Same month";
  }
  if (value > 0) {
    return `${value} mo ahead`;
  }
  return `${Math.abs(value)} mo after`;
}

function getNonZeroMonthSummary(
  monthValues: Array<{ month: string; amount: number }>,
  currencyCode: string,
) {
  return monthValues.filter((value) => value.amount > 0).map((value) => (
    <span
      className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700"
      key={value.month}
    >
      {formatDashboardMonth(value.month)} {formatMatrixCurrency(value.amount, currencyCode)}
    </span>
  ));
}

function readSummaryValue(
  summary: { [key: string]: unknown } | null | undefined,
  key: string,
): string | number | null {
  if (!summary || !(key in summary)) {
    return null;
  }

  const value = summary[key];
  if (typeof value === "string" || typeof value === "number") {
    return value;
  }

  return null;
}

function ForecastRevenueStatusChart({
  currencyCode,
  forecastRevenue,
}: {
  currencyCode: string;
  forecastRevenue: ForecastRevenueSection;
}) {
  const width = Math.max(720, forecastRevenue.months.length * 72);
  const height = 260;
  const paddingX = 40;
  const paddingY = 28;
  const bidValues = forecastRevenue.monthlyStatusTotals.map((month) => month.bidAmount);
  const weightedBidValues = forecastRevenue.monthlyStatusTotals.map(
    (month) => month.weightedBidAmount,
  );
  const bookedValues = forecastRevenue.monthlyStatusTotals.map(
    (month) => month.bookedAmount,
  );
  const lostValues = forecastRevenue.monthlyStatusTotals.map((month) => month.lostAmount);
  const maxValue = getMaxValue([
    ...bidValues,
    ...weightedBidValues,
    ...bookedValues,
    ...lostValues,
  ]);
  const labelStep =
    forecastRevenue.months.length > 18
      ? 3
      : forecastRevenue.months.length > 12
        ? 2
        : 1;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 text-xs text-slate-500">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
          Bid forecast
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-slate-900" />
          Weighted pipeline
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
          Booked / awarded
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
          Lost
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-4">
        <svg
          aria-label="Forecast revenue by status"
          className="h-auto w-full"
          style={{ minWidth: `${width}px` }}
          viewBox={`0 0 ${width} ${height}`}
        >
          {[0, 0.5, 1].map((tick) => {
            const y = height - paddingY - tick * (height - paddingY * 2);

            return (
              <g key={tick}>
                <line
                  stroke="#cbd5e1"
                  strokeDasharray="4 4"
                  strokeWidth="1"
                  x1={paddingX}
                  x2={width - paddingX}
                  y1={y}
                  y2={y}
                />
                <text
                  fill="#64748b"
                  fontSize="11"
                  textAnchor="start"
                  x={0}
                  y={y + 4}
                >
                  {formatCurrency(maxValue * tick, currencyCode)}
                </text>
              </g>
            );
          })}

          <polyline
            fill="none"
            points={getLinePoints(bidValues, width, height, paddingX, paddingY)}
            stroke="#f59e0b"
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeWidth="3"
          />
          <polyline
            fill="none"
            points={getLinePoints(weightedBidValues, width, height, paddingX, paddingY)}
            stroke="#0f172a"
            strokeDasharray="6 4"
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeWidth="3"
          />
          <polyline
            fill="none"
            points={getLinePoints(bookedValues, width, height, paddingX, paddingY)}
            stroke="#10b981"
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeWidth="3"
          />
          <polyline
            fill="none"
            points={getLinePoints(lostValues, width, height, paddingX, paddingY)}
            stroke="#f43f5e"
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeWidth="3"
          />

          {forecastRevenue.monthlyStatusTotals.map((month, index) => {
            const x =
              forecastRevenue.months.length === 1
                ? width / 2
                : paddingX +
                  ((width - paddingX * 2) / (forecastRevenue.months.length - 1)) *
                    index;

            return (
              <g key={month.month}>
                <line
                  stroke="#e2e8f0"
                  strokeWidth="1"
                  x1={x}
                  x2={x}
                  y1={paddingY}
                  y2={height - paddingY}
                />
                {index % labelStep === 0 ? (
                  <text
                    fill="#64748b"
                    fontSize="11"
                    textAnchor="middle"
                    x={x}
                    y={height - 6}
                  >
                    {formatDashboardMonth(month.month)}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

function ForecastRevenueStatusTotals({
  currencyCode,
  totals,
}: {
  currencyCode: string;
  totals: ForecastRevenueSection["overallStatusTotals"];
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="min-w-full border-separate border-spacing-0 text-sm">
        <thead className="bg-white">
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="border-b border-slate-200 px-4 py-3 font-medium">Status</th>
            <th className="border-b border-slate-200 px-4 py-3 font-medium">Projects</th>
            <th className="border-b border-slate-200 px-4 py-3 font-medium">
              Window total
            </th>
            <th className="border-b border-slate-200 px-4 py-3 font-medium">
              Weighted total
            </th>
          </tr>
        </thead>
        <tbody>
          {totals.map((item, index) => (
            <tr className={index % 2 === 0 ? "bg-white" : "bg-slate-50/70"} key={item.status}>
              <td className="border-b border-slate-100 px-4 py-3">
                <span
                  className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getStatusToneClass(item.status)}`}
                >
                  {item.label}
                </span>
              </td>
              <td className="border-b border-slate-100 px-4 py-3 text-slate-700">
                {item.projectCount}
              </td>
              <td className="border-b border-slate-100 px-4 py-3 text-slate-700">
                {formatCurrency(item.totalAmount, currencyCode)}
              </td>
              <td className="border-b border-slate-100 px-4 py-3 text-slate-700">
                {formatCurrency(item.weightedTotalAmount, currencyCode)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProjectDetailRow({
  currencyCode,
  row,
}: {
  currencyCode: string;
  row: ForecastRevenueProjectRow;
}) {
  const changeSummary = row.changeSummary;
  const explanationSummary = row.explanationSummary;
  const methodologySummary = readSummaryValue(explanationSummary, "methodologySummary");
  const changedMonthCount = readSummaryValue(changeSummary, "changedMonthCount");
  const changeReason = readSummaryValue(changeSummary, "reason");
  const totalAmountDelta = readSummaryValue(changeSummary, "totalAmountDelta");

  return (
    <div className="space-y-4 rounded-lg bg-slate-50 p-4">
      <div className="flex flex-wrap gap-2 text-xs text-slate-600">
        <span className="rounded-full bg-white px-2.5 py-1">
          Scenario {formatStatusLabel(row.scenarioKey ?? "base")}
        </span>
        <span className="rounded-full bg-white px-2.5 py-1">
          Forecast {row.forecastStatus ? formatStatusLabel(row.forecastStatus) : "None"}
        </span>
        <span className="rounded-full bg-white px-2.5 py-1">
          Base phasing {formatStatusLabel(row.basePhasingProfile)}
        </span>
        <span className="rounded-full bg-white px-2.5 py-1">
          Method {formatStatusLabel(row.forecastMethod)}
        </span>
        <span className="rounded-full bg-white px-2.5 py-1">
          Manual overrides {row.manualOverrideLineCount}
        </span>
        {row.forecastVersionId ? (
          <span className="rounded-full bg-white px-2.5 py-1">
            Version {row.forecastVersionId.slice(-8)}
          </span>
        ) : null}
        <Link
          className="rounded-full bg-white px-2.5 py-1 font-medium text-slate-900 underline"
          href={`/projects/phasing?projectId=${row.projectId}`}
        >
          Open Revenue Phasing
        </Link>
      </div>

      {methodologySummary || changeReason || changedMonthCount || totalAmountDelta ? (
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border border-slate-200 bg-white p-3">
            <p className="text-xs uppercase tracking-wide text-slate-500">Phasing reason</p>
            <p className="mt-1 text-sm text-slate-700">
              {methodologySummary
                ? String(methodologySummary)
                : "No methodology summary recorded."}
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-3">
            <p className="text-xs uppercase tracking-wide text-slate-500">Version change</p>
            <p className="mt-1 text-sm text-slate-700">
              {changeReason ? String(changeReason) : "No explicit revision reason."}
            </p>
            {changedMonthCount != null ? (
              <p className="mt-1 text-xs text-slate-500">
                {changedMonthCount} months changed
              </p>
            ) : null}
            {typeof totalAmountDelta === "number" ? (
              <p className="mt-1 text-xs text-slate-500">
                Total delta {formatCurrency(totalAmountDelta, currencyCode)}
              </p>
            ) : null}
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-3">
            <p className="text-xs uppercase tracking-wide text-slate-500">
              Quote to execution
            </p>
            <p className="mt-1 text-sm text-slate-700">
              {formatLeadMonths(row.quoteToExecutionLeadMonths)}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Quote {row.quoteEntryDate ? formatDate(row.quoteEntryDate) : "Not set"}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Exec {row.executionStartDate ? formatDate(row.executionStartDate) : "Not set"} to{" "}
              {row.executionEndDate ? formatDate(row.executionEndDate) : "Not set"}
            </p>
          </div>
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full border-separate border-spacing-0 text-sm">
          <thead className="bg-white">
            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="border-b border-slate-200 px-4 py-3 font-medium">Discipline</th>
              <th className="border-b border-slate-200 px-4 py-3 font-medium">Base phasing</th>
              <th className="border-b border-slate-200 px-4 py-3 font-medium">Method</th>
              <th className="border-b border-slate-200 px-4 py-3 font-medium">Overrides</th>
              <th className="border-b border-slate-200 px-4 py-3 font-medium">Total</th>
              <th className="border-b border-slate-200 px-4 py-3 font-medium">Monthly phasing</th>
            </tr>
          </thead>
          <tbody>
            {row.disciplineRows.map((detail, index) => (
              <tr className={index % 2 === 0 ? "bg-white" : "bg-slate-50/70"} key={detail.disciplineId}>
                <td className="border-b border-slate-100 px-4 py-3 font-medium text-slate-900">
                  {detail.disciplineName}
                </td>
                <td className="border-b border-slate-100 px-4 py-3 text-slate-700">
                  {formatStatusLabel(detail.basePhasingProfile)}
                </td>
                <td className="border-b border-slate-100 px-4 py-3 text-slate-700">
                  {formatStatusLabel(detail.forecastMethod)}
                </td>
                <td className="border-b border-slate-100 px-4 py-3 text-slate-700">
                  {detail.manualOverrideLineCount}
                </td>
                <td className="border-b border-slate-100 px-4 py-3 text-slate-700">
                  {formatCurrency(detail.totalAmount, currencyCode)}
                </td>
                <td className="border-b border-slate-100 px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    {getNonZeroMonthSummary(detail.monthValues, currencyCode)}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ForecastRevenueProjectMatrix({
  currencyCode,
  forecastRevenue,
}: {
  currencyCode: string;
  forecastRevenue: ForecastRevenueSection;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("executionStartDate");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");
  const [expandedProjectIds, setExpandedProjectIds] = useState<string[]>([]);

  function toggleSort(nextKey: SortKey) {
    if (nextKey === sortKey) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }

    setSortKey(nextKey);
    setSortDirection(getDefaultDirection(nextKey));
  }

  function isExpanded(projectId: string) {
    return expandedProjectIds.includes(projectId);
  }

  function toggleExpanded(projectId: string) {
    setExpandedProjectIds((current) =>
      current.includes(projectId)
        ? current.filter((item) => item !== projectId)
        : [...current, projectId],
    );
  }

  const sortedRows = forecastRevenue.projectRows.slice().sort((left, right) => {
    const direction = sortDirection === "asc" ? 1 : -1;

    switch (sortKey) {
      case "projectName":
        return compareNullableString(left.projectName, right.projectName) * direction;
      case "clientName":
        return compareNullableString(left.clientName, right.clientName) * direction;
      case "status":
        return compareNullableString(left.status, right.status) * direction;
      case "executionStartDate":
        return (
          compareNullableString(left.executionStartDate, right.executionStartDate) *
          direction
        );
      case "quoteToExecutionLeadMonths":
        return (
          compareNullableNumber(
            left.quoteToExecutionLeadMonths,
            right.quoteToExecutionLeadMonths,
          ) * direction
        );
      case "windowRevenue":
        return compareNullableNumber(left.windowRevenue, right.windowRevenue) * direction;
      case "totalRevenue":
        return compareNullableNumber(left.totalRevenue, right.totalRevenue) * direction;
      default:
        return 0;
    }
  });

  if (sortedRows.length === 0) {
    return (
      <EmptyState
        title="No forecast revenue rows"
        description="Widen the month window or clear narrow filters to inspect project phasing."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
        <p>
          Scroll horizontally for month columns. This is a read-only portfolio report. Expand a
          project row to inspect discipline phasing, overrides, and version context, then open
          Revenue Phasing to edit monthly values.
        </p>
        <p>{sortedRows.length} projects in view</p>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="min-w-full border-separate border-spacing-0 text-sm">
          <thead className="sticky top-0 z-20 bg-white">
            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="sticky left-0 z-20 min-w-[18rem] border-b border-slate-200 bg-white px-4 py-3 font-medium">
                <button onClick={() => toggleSort("projectName")} type="button">
                  Project / Client
                </button>
              </th>
              <th className="border-b border-slate-200 px-4 py-3 font-medium">
                <button onClick={() => toggleSort("status")} type="button">
                  Status
                </button>
              </th>
              <th className="border-b border-slate-200 px-4 py-3 font-medium">Quote entry</th>
              <th className="border-b border-slate-200 px-4 py-3 font-medium">
                <button onClick={() => toggleSort("executionStartDate")} type="button">
                  Exec window
                </button>
              </th>
              <th className="border-b border-slate-200 px-4 py-3 font-medium">
                <button onClick={() => toggleSort("quoteToExecutionLeadMonths")} type="button">
                  Lead
                </button>
              </th>
              <th className="border-b border-slate-200 px-4 py-3 font-medium">Base phasing</th>
              <th className="border-b border-slate-200 px-4 py-3 font-medium">
                <button onClick={() => toggleSort("totalRevenue")} type="button">
                  Total
                </button>
              </th>
              <th className="border-b border-slate-200 px-4 py-3 font-medium">
                <button onClick={() => toggleSort("windowRevenue")} type="button">
                  In window
                </button>
              </th>
              {forecastRevenue.months.map((month) => (
                <th
                  className="border-b border-slate-200 px-3 py-3 text-right font-medium"
                  key={month}
                >
                  {formatDashboardMonth(month)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row, index) => (
              <Fragment key={row.projectId}>
                <tr
                  className={index % 2 === 0 ? "bg-white" : "bg-slate-50/70"}
                >
                  <td className="sticky left-0 z-10 border-b border-slate-100 bg-inherit px-4 py-3">
                    <div className="flex items-start gap-3">
                      <button
                        className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700"
                        onClick={() => toggleExpanded(row.projectId)}
                        type="button"
                      >
                        {isExpanded(row.projectId) ? "-" : "+"}
                      </button>
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-900">{row.projectName}</p>
                        <p className="truncate text-xs text-slate-500">{row.clientName}</p>
                      </div>
                    </div>
                  </td>
                  <td className="border-b border-slate-100 px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getStatusToneClass(row.status)}`}
                    >
                      {formatStatusLabel(row.status)}
                    </span>
                  </td>
                  <td className="border-b border-slate-100 px-4 py-3 text-slate-700">
                    {row.quoteEntryDate ? formatDate(row.quoteEntryDate) : "—"}
                  </td>
                  <td className="border-b border-slate-100 px-4 py-3 text-slate-700">
                    <p>{row.executionStartDate ? formatDate(row.executionStartDate) : "—"}</p>
                    <p className="text-xs text-slate-500">
                      {row.executionEndDate ? formatDate(row.executionEndDate) : "—"}
                    </p>
                  </td>
                  <td className="border-b border-slate-100 px-4 py-3 text-slate-700">
                    {formatLeadMonths(row.quoteToExecutionLeadMonths)}
                  </td>
                  <td className="border-b border-slate-100 px-4 py-3 text-slate-700">
                    <p>{formatStatusLabel(row.basePhasingProfile)}</p>
                    <p className="text-xs text-slate-500">
                      {formatStatusLabel(row.forecastMethod)}
                    </p>
                  </td>
                  <td className="border-b border-slate-100 px-4 py-3 text-slate-700">
                    {formatCurrency(row.totalRevenue, currencyCode)}
                  </td>
                  <td className="border-b border-slate-100 px-4 py-3 text-slate-700">
                    {formatCurrency(row.windowRevenue, currencyCode)}
                  </td>
                  {row.monthValues.map((value) => (
                    <td
                      className="border-b border-slate-100 px-3 py-3 text-right text-slate-700"
                      key={`${row.projectId}-${value.month}`}
                    >
                      {formatMatrixCurrency(value.amount, currencyCode)}
                    </td>
                  ))}
                </tr>
                {isExpanded(row.projectId) ? (
                  <tr>
                    <td
                      className="border-b border-slate-200 px-4 py-4"
                      colSpan={8 + forecastRevenue.months.length}
                    >
                      <ProjectDetailRow currencyCode={currencyCode} row={row} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ForecastRevenueWorkspace({
  forecastRevenue,
}: {
  forecastRevenue: ForecastRevenueSection;
}) {
  const overallTotalsByStatus = Object.fromEntries(
    forecastRevenue.overallStatusTotals.map((item) => [item.status, item]),
  );
  const bidTotal = overallTotalsByStatus.bid?.totalAmount ?? 0;
  const weightedBidTotal = overallTotalsByStatus.bid?.weightedTotalAmount ?? 0;
  const bookedTotal = forecastRevenue.monthlyStatusTotals.reduce(
    (sum, item) => sum + item.bookedAmount,
    0,
  );
  const lostTotal = overallTotalsByStatus.lost?.totalAmount ?? 0;

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryStat
          label="Bid forecast"
          value={formatCurrency(bidTotal, forecastRevenue.currencyCode)}
        />
        <SummaryStat
          label="Weighted pipeline"
          value={formatCurrency(weightedBidTotal, forecastRevenue.currencyCode)}
        />
        <SummaryStat
          label="Booked / awarded"
          value={formatCurrency(bookedTotal, forecastRevenue.currencyCode)}
        />
        <SummaryStat
          label="Lost in view"
          value={formatCurrency(lostTotal, forecastRevenue.currencyCode)}
          tone={lostTotal > 0 ? "warning" : "default"}
        />
      </section>

      <ForecastRevenueStatusChart
        currencyCode={forecastRevenue.currencyCode}
        forecastRevenue={forecastRevenue}
      />

      <ForecastRevenueStatusTotals
        currencyCode={forecastRevenue.currencyCode}
        totals={forecastRevenue.overallStatusTotals}
      />

      <ForecastRevenueProjectMatrix
        currencyCode={forecastRevenue.currencyCode}
        forecastRevenue={forecastRevenue}
      />
    </div>
  );
}
