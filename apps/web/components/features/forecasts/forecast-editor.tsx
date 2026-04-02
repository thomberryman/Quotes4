"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import type {
  AuditEventSummary,
  ForecastDetailRead,
  ForecastLineRead,
  ForecastPolicySummary,
  ForecastSanityCheckRead,
  ForecastVersionRead,
  ProjectScheduleRangeRead,
} from "@quotes4/contracts";
import { ApiClientError } from "@quotes4/contracts";

import { getBrowserApiClient } from "@/lib/api/browser-client";
import { cn } from "@/lib/classnames";
import {
  formatCurrency,
  formatDate,
  formatDateTime,
  formatPercent,
  formatStatusLabel,
} from "@/lib/format";
import { queryKeys } from "@/lib/query/keys";

import {
  type ForecastMonthlyComparisonRow,
  buildForecastMonthlyComparisonRows,
  buildForecastScenarioOptions,
  getDefaultForecastComparisonVersionId,
  summarizeForecastSanityChecks,
  summarizeForecastProjectRollups,
} from "./forecast-editor-helpers";
import { InlineActionBar } from "@/components/forms/inline-action-bar";
import { SegmentedControl } from "@/components/forms/segmented-control";
import { SelectField } from "@/components/forms/select-field";
import { TextAreaField } from "@/components/forms/text-area-field";
import { TextInput } from "@/components/forms/text-input";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SummaryStat } from "@/components/ui/summary-stat";

type AllocationMethod = "manual" | "schedule";
type MonthlyViewMode = "cards" | "table";
type LifecycleAction = "submit" | "lock";

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

type InsightTone = "slate" | "sky" | "amber" | "emerald" | "rose";

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
      amount: String(allocation.amount),
    })),
  };
}

function toLineDraftState(version: ForecastVersionRead | null): LineDraftState {
  if (!version) {
    return {};
  }

  return Object.fromEntries(
    version.lines.map((line) => [line.id, buildLineDraft(line)]),
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
    range.endDate,
  )}${percentLabel}`;
}

function getScheduleRangeOptions(
  line: ForecastLineRead,
  projectScheduleRanges: ProjectScheduleRangeRead[],
): ProjectScheduleRangeRead[] {
  return projectScheduleRanges.filter((range) => {
    if (line.scheduleRangeId && range.id === line.scheduleRangeId) {
      return true;
    }

    return (
      range.disciplineId === line.disciplineId || range.disciplineId == null
    );
  });
}

function summarizePolicyLabels(
  items: Array<{ label: string }>,
  maxItems = 4,
): string {
  if (items.length === 0) {
    return "None configured";
  }

  const labels = items.slice(0, maxItems).map((item) => item.label);
  if (items.length <= maxItems) {
    return labels.join(", ");
  }

  return `${labels.join(", ")} +${items.length - maxItems} more`;
}

function describeAuditEvent(event: AuditEventSummary): string {
  if (event.summary) {
    return event.summary;
  }

  return formatStatusLabel(event.action);
}

function formatAmountRange(
  lowAmount: number | null | undefined,
  highAmount: number | null | undefined,
  currencyCode = "GBP",
) {
  if (lowAmount == null || highAmount == null) {
    return "Not available";
  }

  return `${formatCurrency(lowAmount, currencyCode)} to ${formatCurrency(highAmount, currencyCode)}`;
}

function formatMonthLabel(value: string): string {
  if (!/^\d{4}-\d{2}$/.test(value)) {
    return value;
  }

  return new Intl.DateTimeFormat("en-GB", {
    month: "short",
    year: "numeric",
  }).format(new Date(`${value}-01T00:00:00Z`));
}

function roundAmount(value: number): number {
  return Number(value.toFixed(2));
}

function formatCurrencyDelta(amount: number, currencyCode = "GBP"): string {
  if (amount === 0) {
    return formatCurrency(0, currencyCode);
  }

  const sign = amount > 0 ? "+" : "-";
  return `${sign}${formatCurrency(Math.abs(amount), currencyCode)}`;
}

function getConfidenceTone(
  score: number | null | undefined,
): "default" | "positive" | "warning" {
  if (score == null) {
    return "default";
  }

  if (score >= 75) {
    return "positive";
  }

  if (score < 55) {
    return "warning";
  }

  return "default";
}

function getConfidenceLabel(score: number | null | undefined): string {
  if (score == null) {
    return "No confidence score";
  }

  if (score >= 75) {
    return "High confidence";
  }

  if (score >= 55) {
    return "Moderate confidence";
  }

  return "Low confidence";
}

function getDeltaTextClass(amount: number): string {
  if (amount > 0) {
    return "text-emerald-700";
  }

  if (amount < 0) {
    return "text-rose-700";
  }

  return "text-slate-600";
}

function summarizeForecastInputs(
  inputs: Record<string, unknown> | null | undefined,
): string | null {
  if (!inputs) {
    return null;
  }

  const parts: string[] = [];
  if (typeof inputs.profileKey === "string" && inputs.profileKey.length > 0) {
    parts.push(`Profile ${formatStatusLabel(inputs.profileKey)}`);
  }
  if (typeof inputs.projectCurveMonthCount === "number") {
    parts.push(`${String(inputs.projectCurveMonthCount)} curve month(s)`);
  }
  if (typeof inputs.actualMonthCount === "number") {
    parts.push(`${String(inputs.actualMonthCount)} actual month(s)`);
  }
  if (
    typeof inputs.appliedScheduleShiftMonths === "number" &&
    inputs.appliedScheduleShiftMonths !== 0
  ) {
    parts.push(`Shift ${inputs.appliedScheduleShiftMonths > 0 ? "+" : ""}${String(inputs.appliedScheduleShiftMonths)} mo`);
  }
  if (
    typeof inputs.durationScaleMultiplier === "number" &&
    Math.abs(inputs.durationScaleMultiplier - 1) >= 0.01
  ) {
    parts.push(`Duration x${inputs.durationScaleMultiplier.toFixed(2)}`);
  }
  if (typeof inputs.quoteVsPredictionDeltaPct === "number") {
    parts.push(
      `Prediction delta ${inputs.quoteVsPredictionDeltaPct > 0 ? "+" : ""}${inputs.quoteVsPredictionDeltaPct.toFixed(1)}%`,
    );
  }

  return parts.length > 0 ? parts.join(" · ") : null;
}

function getChangedMonths(
  changeSummary: Record<string, unknown> | null,
): string[] {
  const changedMonths = changeSummary?.changedMonths;
  if (!Array.isArray(changedMonths)) {
    return [];
  }

  return changedMonths.filter((item): item is string => typeof item === "string");
}

function sumDraftAllocations(allocations: AllocationDraft[]): number {
  return roundAmount(
    allocations.reduce((sum, allocation) => {
      const amount = Number(allocation.amount);
      return Number.isFinite(amount) ? sum + amount : sum;
    }, 0),
  );
}

function toBandPosition(value: number, maxAmount: number): number {
  if (maxAmount <= 0) {
    return 0;
  }

  return Math.max(0, Math.min((value / maxAmount) * 100, 100));
}

function getLinePriority(line: ForecastLineRead): number {
  let score = 0;

  if (line.allocationMethod === "manual") {
    score -= 5;
  }
  if (line.issues.length > 0) {
    score -= 3;
  }
  if ((line.sanityChecks?.length ?? 0) > 0) {
    score -= 2;
  }
  if ((line.actualsToDateAmount ?? 0) > 0) {
    score -= 2;
  }
  if (line.confidenceScore != null && line.confidenceScore < 55) {
    score -= 1;
  }

  return score;
}

function InsightBadge({
  label,
  tone = "slate",
}: {
  label: string;
  tone?: InsightTone;
}) {
  const toneClasses: Record<InsightTone, string> = {
    slate: "border-slate-200 bg-slate-100 text-slate-700",
    sky: "border-sky-200 bg-sky-50 text-sky-700",
    amber: "border-amber-200 bg-amber-50 text-amber-800",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-800",
    rose: "border-rose-200 bg-rose-50 text-rose-700",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold",
        toneClasses[tone],
      )}
    >
      {label}
    </span>
  );
}

function isBlockingCheck(check: ForecastSanityCheckRead): boolean {
  return Boolean(check.blocking) || check.severity === "error";
}

function getSanityCheckTone(check: ForecastSanityCheckRead): InsightTone {
  return isBlockingCheck(check) ? "rose" : "amber";
}

function getSanitySurfaceClass(checks: ForecastSanityCheckRead[]): string {
  if (checks.some(isBlockingCheck)) {
    return "border-rose-300 bg-rose-50/40";
  }
  if (checks.length > 0) {
    return "border-amber-300 bg-amber-50/40";
  }
  return "border-slate-200 bg-white";
}

function SanityCheckBadges({
  checks,
  maxItems = 3,
}: {
  checks: ForecastSanityCheckRead[];
  maxItems?: number;
}) {
  if (checks.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {checks.slice(0, maxItems).map((check) => (
        <InsightBadge
          key={`${check.key}:${check.lineId ?? ""}:${check.month ?? ""}:${check.title}`}
          label={check.title}
          tone={getSanityCheckTone(check)}
        />
      ))}
      {checks.length > maxItems ? (
        <InsightBadge
          label={`+${String(checks.length - maxItems)} more`}
          tone={checks.some(isBlockingCheck) ? "rose" : "amber"}
        />
      ) : null}
    </div>
  );
}

function SanityCheckList({
  checks,
  lineLabelsById,
}: {
  checks: ForecastSanityCheckRead[];
  lineLabelsById?: Record<string, string>;
}) {
  if (checks.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      {checks.map((check) => {
        const lineLabel =
          check.lineId != null ? lineLabelsById?.[check.lineId] ?? check.lineId : null;

        return (
          <div
            className={cn(
              "rounded-lg border px-4 py-3 text-sm",
              isBlockingCheck(check)
                ? "border-rose-200 bg-rose-50 text-rose-950"
                : "border-amber-200 bg-amber-50 text-amber-950",
            )}
            key={`${check.key}:${check.lineId ?? ""}:${check.month ?? ""}:${check.title}`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-semibold">{check.title}</p>
              <InsightBadge
                label={isBlockingCheck(check) ? "Blocking" : "Warning"}
                tone={getSanityCheckTone(check)}
              />
              {lineLabel ? <InsightBadge label={lineLabel} tone="slate" /> : null}
              {check.month ? (
                <InsightBadge label={formatMonthLabel(check.month)} tone="slate" />
              ) : null}
            </div>
            <p className="mt-2">{check.detail}</p>
            {check.recommendation ? (
              <p className="mt-2 text-xs font-medium uppercase tracking-[0.12em]">
                {check.recommendation}
              </p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function MonthlyBandBar({
  amount,
  currencyCode,
  lowAmount,
  highAmount,
  actualAmount,
  comparisonAmount,
  maxAmount,
}: {
  amount: number;
  currencyCode: string;
  lowAmount: number | null;
  highAmount: number | null;
  actualAmount: number | null;
  comparisonAmount: number | null;
  maxAmount: number;
}) {
  const amountPosition = toBandPosition(amount, maxAmount);
  const comparisonPosition =
    comparisonAmount != null ? toBandPosition(comparisonAmount, maxAmount) : null;
  const actualPosition =
    actualAmount != null ? toBandPosition(actualAmount, maxAmount) : null;
  const lowPosition =
    lowAmount != null ? toBandPosition(lowAmount, maxAmount) : null;
  const highPosition =
    highAmount != null ? toBandPosition(highAmount, maxAmount) : null;
  const bandWidth =
    lowPosition != null && highPosition != null
      ? Math.max(highPosition - lowPosition, 1.5)
      : null;

  return (
    <div className="space-y-2">
      <div className="relative h-2 rounded-full bg-slate-200">
        {lowPosition != null && bandWidth != null ? (
          <div
            className="absolute top-0 h-2 rounded-full bg-sky-200"
            style={{
              left: `${lowPosition}%`,
              width: `${bandWidth}%`,
            }}
          />
        ) : null}
        {comparisonPosition != null ? (
          <div
            className="absolute top-1/2 h-4 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-500"
            style={{ left: `${comparisonPosition}%` }}
          />
        ) : null}
        {actualPosition != null ? (
          <div
            className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-emerald-600 bg-white"
            style={{ left: `${actualPosition}%` }}
          />
        ) : null}
        <div
          className="absolute top-1/2 h-4 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-900"
          style={{ left: `${amountPosition}%` }}
        />
      </div>
      <div className="flex items-center justify-between text-[11px] font-medium text-slate-500">
        <span>
          Low{" "}
          {lowAmount != null
            ? formatCurrency(lowAmount, currencyCode)
            : "Not available"}
        </span>
        <span>
          High{" "}
          {highAmount != null
            ? formatCurrency(highAmount, currencyCode)
            : "Not available"}
        </span>
      </div>
    </div>
  );
}

function MonthlyRollupCard({
  checks,
  currencyCode,
  maxAmount,
  row,
  comparisonVersionLabel,
}: {
  checks: ForecastSanityCheckRead[];
  currencyCode: string;
  maxAmount: number;
  row: ForecastMonthlyComparisonRow;
  comparisonVersionLabel?: string;
}) {
  return (
    <article
      className={cn(
        "rounded-xl border p-4 shadow-sm",
        getSanitySurfaceClass(checks),
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-900">
            {formatMonthLabel(row.month)}
          </p>
          <p className="mt-1 text-xs text-slate-500">{row.month}</p>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          {row.actualAmount != null ? (
            <InsightBadge label="Actuals posted" tone="emerald" />
          ) : (
            <InsightBadge label="Forecast month" tone="sky" />
          )}
          <SanityCheckBadges checks={checks} maxItems={2} />
        </div>
      </div>

      {checks.length > 0 ? (
        <div
          className={cn(
            "mt-3 rounded-lg border px-3 py-2 text-sm",
            checks.some(isBlockingCheck)
              ? "border-rose-200 bg-rose-50 text-rose-900"
              : "border-amber-200 bg-amber-50 text-amber-900",
          )}
        >
          {checks[0]?.detail}
        </div>
      ) : null}

      <p className="mt-4 text-2xl font-semibold text-slate-900">
        {formatCurrency(row.amount, currencyCode)}
      </p>
      <p className="mt-1 text-sm text-slate-600">
        Weighted {formatCurrency(row.weightedAmount, currencyCode)}
      </p>

      <div className="mt-4">
        <MonthlyBandBar
          actualAmount={row.actualAmount}
          amount={row.amount}
          comparisonAmount={row.comparisonAmount}
          currencyCode={currencyCode}
          highAmount={row.highAmount}
          lowAmount={row.lowAmount}
          maxAmount={maxAmount}
        />
      </div>

      <div className="mt-4 grid gap-2 text-sm text-slate-600 sm:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
            Confidence Band
          </p>
          <p className="mt-1 text-sm font-medium text-slate-900">
            {formatAmountRange(row.lowAmount, row.highAmount, currencyCode)}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
            Compare Delta
          </p>
          <p
            className={cn(
              "mt-1 text-sm font-medium",
              getDeltaTextClass(row.deltaAmount),
            )}
          >
            {row.comparisonAmount != null
              ? formatCurrencyDelta(row.deltaAmount, currencyCode)
              : "No comparison month"}
          </p>
          {comparisonVersionLabel ? (
            <p className="mt-1 text-xs text-slate-500">
              {comparisonVersionLabel}
              {row.comparisonAmount != null
                ? ` at ${formatCurrency(row.comparisonAmount, currencyCode)}`
                : " has no value for this month."}
            </p>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function MonthlyComparisonTable({
  checksByMonth,
  comparisonVersionLabel,
  currencyCode,
  rows,
}: {
  checksByMonth: Record<string, ForecastSanityCheckRead[]>;
  comparisonVersionLabel?: string;
  currencyCode: string;
  rows: ForecastMonthlyComparisonRow[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-slate-600">
          <tr>
            <th className="px-3 py-2 font-medium">Month</th>
            <th className="px-3 py-2 font-medium">Forecast</th>
            <th className="px-3 py-2 font-medium">Weighted</th>
            <th className="px-3 py-2 font-medium">Band</th>
            <th className="px-3 py-2 font-medium">Actuals</th>
            <th className="px-3 py-2 font-medium">
              {comparisonVersionLabel ?? "Comparison"}
            </th>
            <th className="px-3 py-2 font-medium">Delta</th>
            <th className="px-3 py-2 font-medium">Warnings</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200">
          {rows.map((row) => {
            const checks = checksByMonth[row.month] ?? [];

            return (
              <tr
                className={cn(
                  checks.some(isBlockingCheck)
                    ? "bg-rose-50/50"
                    : checks.length > 0
                      ? "bg-amber-50/40"
                      : "",
                )}
                key={row.month}
              >
                <td className="px-3 py-2 font-medium text-slate-900">
                  {formatMonthLabel(row.month)}
                </td>
                <td className="px-3 py-2 text-slate-700">
                  {formatCurrency(row.amount, currencyCode)}
                </td>
                <td className="px-3 py-2 text-slate-700">
                  {formatCurrency(row.weightedAmount, currencyCode)}
                </td>
                <td className="px-3 py-2 text-slate-700">
                  {formatAmountRange(row.lowAmount, row.highAmount, currencyCode)}
                </td>
                <td className="px-3 py-2 text-slate-700">
                  {row.actualAmount != null
                    ? formatCurrency(row.actualAmount, currencyCode)
                    : "None"}
                </td>
                <td className="px-3 py-2 text-slate-700">
                  {row.comparisonAmount != null
                    ? formatCurrency(row.comparisonAmount, currencyCode)
                    : "None"}
                </td>
                <td
                  className={cn(
                    "px-3 py-2 font-medium",
                    getDeltaTextClass(row.deltaAmount),
                  )}
                >
                  {formatCurrencyDelta(row.deltaAmount, currencyCode)}
                </td>
                <td className="px-3 py-2 text-slate-700">
                  {checks.length > 0 ? (
                    <SanityCheckBadges checks={checks} maxItems={2} />
                  ) : (
                    <span className="text-slate-400">None</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function ForecastEditor({
  projectId,
  initialForecast,
  initialPolicy,
  projectScheduleRanges,
}: {
  projectId: string;
  initialForecast: ForecastDetailRead;
  initialPolicy: ForecastPolicySummary;
  projectScheduleRanges: ProjectScheduleRangeRead[];
}) {
  const api = getBrowserApiClient();
  const queryClient = useQueryClient();
  const [selectedVersionId, setSelectedVersionId] = useState(
    initialForecast.currentVersionId ?? initialForecast.versions[0]?.id ?? "",
  );
  const [comparisonVersionId, setComparisonVersionId] = useState("");
  const [monthlyViewMode, setMonthlyViewMode] =
    useState<MonthlyViewMode>("cards");
  const [title, setTitle] = useState("");
  const [notesText, setNotesText] = useState("");
  const [probabilityPercent, setProbabilityPercent] = useState("100");
  const [revisionReason, setRevisionReason] = useState("");
  const [lineDrafts, setLineDrafts] = useState<LineDraftState>({});
  const [pendingLifecycleAction, setPendingLifecycleAction] =
    useState<LifecycleAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const forecastQuery = useQuery({
    initialData: initialForecast,
    queryFn: async () => api.getProjectForecast(projectId),
    queryKey: queryKeys.projectForecast(projectId),
  });

  const policyQuery = useQuery({
    initialData: initialPolicy,
    queryFn: async () => api.getForecastPolicy(),
    queryKey: queryKeys.forecastPolicy,
  });

  const auditQuery = useQuery({
    queryFn: async () => api.listAuditEvents({ limit: 12, projectId }),
    queryKey: queryKeys.auditEvents(projectId),
    retry: false,
  });

  useEffect(() => {
    const fallbackVersionId =
      forecastQuery.data.currentVersionId ?? forecastQuery.data.versions[0]?.id ?? "";

    if (!fallbackVersionId) {
      return;
    }

    if (
      !selectedVersionId ||
      !forecastQuery.data.versions.some((version) => version.id === selectedVersionId)
    ) {
      setSelectedVersionId(fallbackVersionId);
    }
  }, [
    forecastQuery.data.currentVersionId,
    forecastQuery.data.versions,
    selectedVersionId,
  ]);

  const selectedVersionSummary = useMemo(
    () =>
      forecastQuery.data.versions.find(
        (version) => version.id === selectedVersionId,
      ) ?? null,
    [forecastQuery.data.versions, selectedVersionId],
  );

  const selectedVersionQuery = useQuery({
    enabled: Boolean(selectedVersionId),
    initialData:
      forecastQuery.data.currentVersion?.id === selectedVersionId
        ? forecastQuery.data.currentVersion
        : undefined,
    placeholderData: (previousData) => previousData,
    queryFn: async () => api.getForecastVersion(selectedVersionId),
    queryKey: queryKeys.forecastVersion(selectedVersionId || "none"),
  });

  const version = selectedVersionQuery.data ?? null;

  useEffect(() => {
    const nextComparisonVersionId = getDefaultForecastComparisonVersionId(
      selectedVersionId,
      version,
      forecastQuery.data.versions,
    );

    setComparisonVersionId((current) => {
      const isCurrentValid =
        current.length > 0 &&
        current !== selectedVersionId &&
        forecastQuery.data.versions.some((item) => item.id === current);

      if (isCurrentValid) {
        return current;
      }

      return nextComparisonVersionId;
    });
  }, [forecastQuery.data.versions, selectedVersionId, version]);

  const comparisonVersionQuery = useQuery({
    enabled: Boolean(
      comparisonVersionId && comparisonVersionId !== selectedVersionId,
    ),
    placeholderData: (previousData) => previousData,
    queryFn: async () => api.getForecastVersion(comparisonVersionId),
    queryKey: queryKeys.forecastVersion(comparisonVersionId || "none"),
  });

  const comparisonVersion =
    comparisonVersionId && comparisonVersionId !== selectedVersionId
      ? comparisonVersionQuery.data ?? null
      : null;

  useEffect(() => {
    if (!version) {
      return;
    }

    setTitle(version.title ?? "");
    setNotesText(version.notesText ?? "");
    setProbabilityPercent(String(version.probabilityPercent));
    setRevisionReason(version.revisionReason ?? "");
    setLineDrafts(toLineDraftState(version));
  }, [version]);

  useEffect(() => {
    setPendingLifecycleAction(null);
  }, [selectedVersionId, version?.status]);

  const clearFeedback = () => {
    setError(null);
    setNotice(null);
  };

  const invalidateForecastData = async (versionId?: string) => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: queryKeys.projectForecast(projectId),
      }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.auditEvents(projectId),
      }),
      versionId
        ? queryClient.invalidateQueries({
            queryKey: queryKeys.forecastVersion(versionId),
          })
        : Promise.resolve(),
    ]);
  };

  const createDraftMutation = useMutation({
    mutationFn: async () =>
      api.createForecastVersion(projectId, {
        baseVersionId: selectedVersionId || null,
        title: title || null,
        notesText: notesText || null,
        probabilityPercent: Number(probabilityPercent),
        revisionReason: revisionReason || null,
      }),
    onMutate: clearFeedback,
    onSuccess: async (createdVersion) => {
      setSelectedVersionId(createdVersion.id);
      setNotice(`Created draft forecast v${createdVersion.versionNumber}.`);
      await invalidateForecastData(createdVersion.id);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not create the forecast draft.",
      );
    },
  });

  const updateVersionMutation = useMutation({
    mutationFn: async () => {
      if (!version) {
        throw new Error("Forecast version missing.");
      }

      return api.updateForecastVersion(version.id, {
        expectedUpdatedAt: version.updatedAt,
        title: title || null,
        notesText: notesText || null,
        probabilityPercent: Number(probabilityPercent),
        revisionReason: revisionReason || null,
      });
    },
    onMutate: clearFeedback,
    onSuccess: async (updatedVersion) => {
      setNotice(`Saved metadata for draft v${updatedVersion.versionNumber}.`);
      await invalidateForecastData(updatedVersion.id);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not save the forecast version.",
      );
    },
  });

  const lineMutation = useMutation({
    mutationFn: async (lineId: string) => {
      const currentVersion = version;
      const line = currentVersion?.lines.find((item) => item.id === lineId);
      const draft = lineDrafts[lineId];

      if (!currentVersion || !line || !draft) {
        throw new Error("Forecast line missing.");
      }

      return api.replaceForecastLineAllocations(lineId, {
        expectedUpdatedAt: currentVersion.updatedAt,
        allocationMethod: draft.allocationMethod,
        allocations:
          draft.allocationMethod === "manual"
            ? draft.allocations
                .filter((allocation) => allocation.month || allocation.amount)
                .map((allocation) => ({
                  month: allocation.month,
                  amount: Number(allocation.amount),
                }))
            : [],
        reason: draft.reason || null,
        scheduleRangeId: draft.scheduleRangeId || null,
      });
    },
    onMutate: clearFeedback,
    onSuccess: async (updatedVersion) => {
      setNotice(
        `Saved line allocations for forecast v${updatedVersion.versionNumber}.`,
      );
      await invalidateForecastData(updatedVersion.id);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not save line allocations.",
      );
    },
  });

  const submitMutation = useMutation({
    mutationFn: async () => {
      if (!selectedVersionId) {
        throw new Error("Forecast version missing.");
      }

      return api.submitForecastVersion(selectedVersionId);
    },
    onMutate: clearFeedback,
    onSuccess: async (submittedVersion) => {
      setPendingLifecycleAction(null);
      setNotice(`Submitted forecast v${submittedVersion.versionNumber}.`);
      await invalidateForecastData(submittedVersion.id);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not submit the forecast version.",
      );
    },
  });

  const lockMutation = useMutation({
    mutationFn: async () => {
      if (!selectedVersionId) {
        throw new Error("Forecast version missing.");
      }

      return api.lockForecastVersion(selectedVersionId);
    },
    onMutate: clearFeedback,
    onSuccess: async (lockedVersion) => {
      setPendingLifecycleAction(null);
      setNotice(`Locked forecast v${lockedVersion.versionNumber}.`);
      await invalidateForecastData(lockedVersion.id);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not lock the forecast version.",
      );
    },
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
          : "Could not recalculate the forecast.",
      );
    },
  });

  const scenarioOptions = useMemo(
    () => buildForecastScenarioOptions(forecastQuery.data.versions),
    [forecastQuery.data.versions],
  );

  const comparisonVersionOptions = useMemo(
    () =>
      forecastQuery.data.versions.filter((item) => item.id !== selectedVersionId),
    [forecastQuery.data.versions, selectedVersionId],
  );

  const currencyCode =
    version?.lines[0]?.currencyCode ??
    comparisonVersion?.lines[0]?.currencyCode ??
    "GBP";

  const selectedScenarioKey =
    version?.scenarioKey ?? selectedVersionSummary?.scenarioKey ?? "base";
  const selectedScenarioOption =
    scenarioOptions.find((item) => item.scenarioKey === selectedScenarioKey) ??
    null;
  const comparisonVersionLabel = comparisonVersion
    ? `V${comparisonVersion.versionNumber}`
    : undefined;
  const sanitySummary = useMemo(
    () => summarizeForecastSanityChecks(forecastQuery.data, version),
    [forecastQuery.data, version],
  );
  const lineLabelsById = useMemo(
    () =>
      Object.fromEntries(
        (version?.lines ?? []).map((line) => [line.id, line.label]),
      ) as Record<string, string>,
    [version?.lines],
  );

  const changeSummary = (version?.changeSummary ?? null) as Record<
    string,
    unknown
  > | null;
  const explanationSummary = (version?.explanationSummary ?? null) as Record<
    string,
    unknown
  > | null;
  const changedMonthCount =
    typeof changeSummary?.changedMonthCount === "number"
      ? changeSummary.changedMonthCount
      : null;
  const changedMonths = getChangedMonths(changeSummary);
  const methodologySummaryText =
    typeof explanationSummary?.methodologySummary === "string"
      ? explanationSummary.methodologySummary
      : "Unified forecast engine with predictive inputs.";
  const actualMonthCount =
    typeof explanationSummary?.actualMonthCount === "number"
      ? explanationSummary.actualMonthCount
      : 0;
  const projectFormatKey =
    typeof explanationSummary?.projectFormatKey === "string"
      ? explanationSummary.projectFormatKey
      : null;
  const isDraftVersion = version?.status === "draft";
  const canSubmitVersion = version?.status === "draft";
  const canLockVersion =
    version?.status === "draft" || version?.status === "submitted";
  const lifecycleBlocked = sanitySummary.allBlockingMessages.length > 0;
  const versionConfidenceChecks = sanitySummary.confidenceChecks.filter(
    (check) => check.scope !== "line",
  );
  const auditUnavailable =
    auditQuery.error instanceof ApiClientError &&
    auditQuery.error.status === 403;

  const monthlyComparisonRows = useMemo(
    () =>
      buildForecastMonthlyComparisonRows(
        version?.projectMonthlyRollups ?? [],
        comparisonVersion?.projectMonthlyRollups ?? [],
      ),
    [comparisonVersion?.projectMonthlyRollups, version?.projectMonthlyRollups],
  );

  const monthlyRollupSummary = useMemo(
    () => summarizeForecastProjectRollups(version?.projectMonthlyRollups ?? []),
    [version?.projectMonthlyRollups],
  );

  const changedComparisonRows = useMemo(
    () =>
      monthlyComparisonRows.filter(
        (row) =>
          Math.abs(row.deltaAmount) > 0.009 || row.comparisonAmount == null,
      ),
    [monthlyComparisonRows],
  );

  const maxMonthlyAmount = useMemo(() => {
    return monthlyComparisonRows.reduce((maxAmount, row) => {
      const rowMax = Math.max(
        row.amount,
        row.lowAmount ?? 0,
        row.highAmount ?? 0,
        row.actualAmount ?? 0,
        row.comparisonAmount ?? 0,
      );
      return Math.max(maxAmount, rowMax);
    }, 0);
  }, [monthlyComparisonRows]);

  const explanationCards = useMemo(() => {
    if (!version) {
      return [];
    }

    return version.lines.flatMap((line) =>
      line.explanations.map((explanation) => ({
        explanation,
        line,
      })),
    );
  }, [version]);

  const sortedLines = useMemo(() => {
    if (!version) {
      return [];
    }

    return version.lines
      .map((line, index) => ({ index, line }))
      .sort((left, right) => {
        const priorityDelta =
          getLinePriority(left.line) - getLinePriority(right.line);

        if (priorityDelta !== 0) {
          return priorityDelta;
        }

        return left.index - right.index;
      })
      .map((item) => item.line);
  }, [version]);

  const manualLineCount =
    version?.lines.filter((line) => line.allocationMethod === "manual").length ?? 0;
  const scheduleLineCount =
    version?.lines.filter((line) => line.allocationMethod !== "manual").length ?? 0;
  const attentionLineCount =
    version?.lines.filter(
      (line) => line.issues.length > 0 || (line.sanityChecks?.length ?? 0) > 0,
    ).length ?? 0;
  const actualBackedLineCount =
    version?.lines.filter((line) => (line.actualsToDateAmount ?? 0) > 0).length ?? 0;

  const comparisonTotalDelta =
    version && comparisonVersion
      ? roundAmount(version.totalAmount - comparisonVersion.totalAmount)
      : null;
  const comparisonWeightedDelta =
    version && comparisonVersion
      ? roundAmount(
          version.weightedTotalAmount - comparisonVersion.weightedTotalAmount,
        )
      : null;
  const comparisonProbabilityDelta =
    version && comparisonVersion
      ? roundAmount(
          version.probabilityPercent - comparisonVersion.probabilityPercent,
        )
      : null;
  const comparisonConfidenceDelta =
    version &&
    comparisonVersion &&
    version.confidenceScore != null &&
    comparisonVersion.confidenceScore != null
      ? roundAmount(version.confidenceScore - comparisonVersion.confidenceScore)
      : null;

  const projectRangeLabel = formatAmountRange(
    monthlyRollupSummary.lowTotal,
    monthlyRollupSummary.highTotal,
    currencyCode,
  );
  const confidenceHint =
    versionConfidenceChecks.length > 0
      ? [
          version?.dataSufficiencyScore != null
            ? `${formatPercent(version.dataSufficiencyScore)} data sufficiency`
            : "No predictive evidence linked",
          ...versionConfidenceChecks.map((check) => check.detail),
        ].join(" · ")
      : version?.dataSufficiencyScore != null
        ? `${formatPercent(version.dataSufficiencyScore)} data sufficiency`
        : "No predictive evidence linked";
  const lifecycleActionLabel =
    pendingLifecycleAction === "lock" ? "lock" : "submit";

  const confirmLifecycleAction = () => {
    if (lifecycleBlocked) {
      return;
    }

    if (pendingLifecycleAction === "submit") {
      submitMutation.mutate();
      return;
    }

    if (pendingLifecycleAction === "lock") {
      lockMutation.mutate();
    }
  };

  if (!version && forecastQuery.data.versions.length === 0) {
    return (
      <div className="space-y-6">
        {error ? (
          <ErrorState description={error} title="Forecast action failed" />
        ) : null}
        {notice ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm text-emerald-900">
            {notice}
          </div>
        ) : null}
        <SectionCard
          title="Forecast Workspace"
          description="Create the first working forecast version for this project."
        >
          <p className="text-sm text-slate-600">
            No forecast versions exist yet. Create an initial draft, then use
            this page to compare scenarios, review confidence bands, and manage
            overrides.
          </p>
          <div className="mt-4">
            <InlineActionBar>
              <Button
                onClick={() => createDraftMutation.mutate()}
                type="button"
                variant="primary"
              >
                {createDraftMutation.isPending ? "Creating..." : "Create first draft"}
              </Button>
            </InlineActionBar>
          </div>
        </SectionCard>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error ? (
        <ErrorState description={error} title="Forecast action failed" />
      ) : null}
      {notice ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm text-emerald-900">
          {notice}
        </div>
      ) : null}

      {sanitySummary.blockingChecks.length > 0 ||
      sanitySummary.otherBlockingIssues.length > 0 ? (
        <section className="rounded-xl border border-rose-300 bg-rose-50 px-5 py-4 shadow-sm">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <h2 className="text-base font-semibold text-rose-950">
                Blocking forecast issues
              </h2>
              <p className="mt-1 max-w-3xl text-sm text-rose-900">
                Resolve these issues before this version can be submitted or
                locked.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <InsightBadge
                label={`${String(sanitySummary.allBlockingMessages.length)} blocker${sanitySummary.allBlockingMessages.length === 1 ? "" : "s"}`}
                tone="rose"
              />
              {sanitySummary.blockingLineIds.length > 0 ? (
                <InsightBadge
                  label={`${String(sanitySummary.blockingLineIds.length)} line${sanitySummary.blockingLineIds.length === 1 ? "" : "s"} affected`}
                  tone="amber"
                />
              ) : null}
              {sanitySummary.blockingMonths.length > 0 ? (
                <InsightBadge
                  label={`${String(sanitySummary.blockingMonths.length)} month${sanitySummary.blockingMonths.length === 1 ? "" : "s"} flagged`}
                  tone="amber"
                />
              ) : null}
            </div>
          </div>

          <div className="mt-4">
            <SanityCheckList
              checks={sanitySummary.blockingChecks}
              lineLabelsById={lineLabelsById}
            />
            {sanitySummary.otherBlockingIssues.length > 0 ? (
              <div className="mt-2 space-y-2">
                {sanitySummary.otherBlockingIssues.map((issue) => (
                  <div
                    className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-950"
                    key={issue}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold">Blocking issue</p>
                      <InsightBadge label="Blocking" tone="rose" />
                    </div>
                    <p className="mt-2">{issue}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </section>
      ) : null}

      {sanitySummary.warningChecks.length > 0 ? (
        <section className="rounded-xl border border-amber-300 bg-amber-50 px-5 py-4 shadow-sm">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <h2 className="text-base font-semibold text-amber-950">
                Forecast warnings
              </h2>
              <p className="mt-1 max-w-3xl text-sm text-amber-900">
                These checks do not block submission, but they do reduce trust
                in the timing, scenario spread, or confidence story.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <InsightBadge
                label={`${String(sanitySummary.warningChecks.length)} warning${sanitySummary.warningChecks.length === 1 ? "" : "s"}`}
                tone="amber"
              />
              {sanitySummary.warningLineIds.length > 0 ? (
                <InsightBadge
                  label={`${String(sanitySummary.warningLineIds.length)} line${sanitySummary.warningLineIds.length === 1 ? "" : "s"} affected`}
                  tone="amber"
                />
              ) : null}
              {sanitySummary.warningMonths.length > 0 ? (
                <InsightBadge
                  label={`${String(sanitySummary.warningMonths.length)} month${sanitySummary.warningMonths.length === 1 ? "" : "s"} flagged`}
                  tone="amber"
                />
              ) : null}
            </div>
          </div>

          <div className="mt-4">
            <SanityCheckBadges checks={sanitySummary.warningChecks} maxItems={6} />
          </div>
          <div className="mt-4">
            <SanityCheckList
              checks={sanitySummary.warningChecks.slice(0, 3)}
              lineLabelsById={lineLabelsById}
            />
          </div>
        </section>
      ) : null}

      {!isDraftVersion ? (
        <SectionCard
          title="Read-Only Version"
          description="Submitted and locked versions stay immutable."
        >
          <p className="text-sm text-slate-600">
            This version is currently{" "}
            {formatStatusLabel(version?.status ?? "unknown").toLowerCase()}. Create
            a draft before changing metadata or line allocations.
          </p>
        </SectionCard>
      ) : null}

      <SectionCard
        title="Working Forecast"
        description="Switch scenario, choose the active version, and keep the forecast lifecycle visible before editing."
      >
        {scenarioOptions.length > 0 ? (
          <div className="grid gap-3 xl:grid-cols-3">
            {scenarioOptions.map((scenario) => {
              const isActive = scenario.scenarioKey === selectedScenarioKey;

              return (
                <button
                  className={cn(
                    "rounded-xl border px-4 py-4 text-left transition",
                    isActive
                      ? "border-slate-900 bg-slate-900 text-white shadow-sm"
                      : "border-slate-200 bg-white text-slate-900 hover:border-slate-300 hover:bg-slate-50",
                  )}
                  key={scenario.scenarioKey}
                  onClick={() => setSelectedVersionId(scenario.latestVersionId)}
                  type="button"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold">{scenario.label}</p>
                    <span
                      className={cn(
                        "rounded-full px-2.5 py-1 text-xs font-semibold",
                        isActive
                          ? "bg-white/10 text-white"
                          : "bg-slate-100 text-slate-700",
                      )}
                    >
                      {scenario.count} version{scenario.count === 1 ? "" : "s"}
                    </span>
                  </div>
                  <p className="mt-3 text-xl font-semibold">
                    {formatCurrency(scenario.weightedTotalAmount, currencyCode)}
                  </p>
                  <p
                    className={cn(
                      "mt-1 text-sm",
                      isActive ? "text-slate-300" : "text-slate-600",
                    )}
                  >
                    Latest v{scenario.latestVersionNumber} ·{" "}
                    {scenario.confidenceScore != null
                      ? `${formatPercent(scenario.confidenceScore)} confidence`
                      : "No confidence score"}
                  </p>
                </button>
              );
            })}
          </div>
        ) : null}

        {sanitySummary.scenarioChecks.length > 0 ? (
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-amber-950">
                Scenario comparison warning
              </p>
              <SanityCheckBadges checks={sanitySummary.scenarioChecks} maxItems={2} />
            </div>
            <div className="mt-3">
              <SanityCheckList checks={sanitySummary.scenarioChecks} />
            </div>
          </div>
        ) : null}

        <div className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,260px)_minmax(0,260px)_1fr]">
          <SelectField
            label="Version"
            onChange={(event) => setSelectedVersionId(event.target.value)}
            value={selectedVersionId}
          >
            {forecastQuery.data.versions.map((forecastVersion) => (
              <option key={forecastVersion.id} value={forecastVersion.id}>
                V{forecastVersion.versionNumber} ·{" "}
                {formatStatusLabel(forecastVersion.status)} ·{" "}
                {formatStatusLabel(forecastVersion.scenarioKey ?? "base")}
              </option>
            ))}
          </SelectField>

          <SelectField
            label="Compare against"
            onChange={(event) => setComparisonVersionId(event.target.value)}
            value={comparisonVersionId}
          >
            {comparisonVersionOptions.length === 0 ? (
              <option value="">No other versions available</option>
            ) : null}
            {comparisonVersionOptions.map((forecastVersion) => (
              <option key={forecastVersion.id} value={forecastVersion.id}>
                V{forecastVersion.versionNumber} ·{" "}
                {formatStatusLabel(forecastVersion.status)} ·{" "}
                {formatStatusLabel(forecastVersion.scenarioKey ?? "base")}
              </option>
            ))}
          </SelectField>

          <div className="rounded-xl border border-slate-900 bg-slate-950 px-5 py-4 text-white">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-lg font-semibold">
                {version?.title ?? `Forecast v${version?.versionNumber ?? "?"}`}
              </p>
              {selectedVersionSummary ? (
                <StatusBadge value={selectedVersionSummary.status} />
              ) : null}
            </div>
            <p className="mt-2 text-sm text-slate-300">
              {formatStatusLabel(selectedScenarioKey)} scenario · Updated{" "}
              {formatDateTime(version?.updatedAt)}
              {version?.parentVersionId
                ? ` · Parent ${version.parentVersionId.slice(0, 8)}`
                : ""}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <InsightBadge
                label={
                  version?.isSourceQuoteCurrent ? "Current quote basis" : "Quote needs rebase"
                }
                tone={version?.isSourceQuoteCurrent ? "emerald" : "amber"}
              />
              <InsightBadge
                label={getConfidenceLabel(version?.confidenceScore)}
                tone={
                  version?.confidenceScore != null && version.confidenceScore < 55
                    ? "amber"
                    : "sky"
                }
              />
              {comparisonVersion ? (
                <InsightBadge
                  label={`Comparing with V${comparisonVersion.versionNumber}`}
                  tone="slate"
                />
              ) : null}
            </div>
            <p className="mt-4 text-sm text-slate-200">
              {revisionReason || version?.revisionReason || methodologySummaryText}
            </p>
          </div>
        </div>

        <div className="mt-4">
          <InlineActionBar>
            <Link
              className="inline-flex items-center justify-center rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-900 transition hover:bg-slate-50"
              href={`/projects/${projectId}/scenarios`}
            >
              Scenario planning
            </Link>
            <Button
              onClick={() => createDraftMutation.mutate()}
              type="button"
              variant="primary"
            >
              {createDraftMutation.isPending ? "Creating..." : "Create draft"}
            </Button>
            <Button
              disabled={
                !selectedVersionId || !canSubmitVersion || submitMutation.isPending
              }
              onClick={() => setPendingLifecycleAction("submit")}
              type="button"
            >
              {submitMutation.isPending ? "Submitting..." : "Submit"}
            </Button>
            <Button
              disabled={
                !selectedVersionId || !canLockVersion || lockMutation.isPending
              }
              onClick={() => setPendingLifecycleAction("lock")}
              type="button"
            >
              {lockMutation.isPending ? "Locking..." : "Lock"}
            </Button>
            <Button
              onClick={() => recalcMutation.mutate()}
              type="button"
              variant="ghost"
            >
              {recalcMutation.isPending ? "Recalculating..." : "Recalculate"}
            </Button>
          </InlineActionBar>
        </div>

        <p className="mt-4 text-sm text-slate-600">
          Supported methods: {policyQuery.data.supportedMethods.join(", ")}.
          Outcomes: {policyQuery.data.supportedOutcomes.join(", ")}. Triggers:{" "}
          {policyQuery.data.recalcTriggers.join(", ")}.
        </p>

        {pendingLifecycleAction ? (
          <div
            className={cn(
              "mt-4 rounded-xl border p-4",
              lifecycleBlocked
                ? "border-rose-300 bg-rose-50"
                : "border-slate-200 bg-slate-50",
            )}
          >
            <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
              <div>
                <p className="text-sm font-semibold text-slate-900">
                  Confirm {lifecycleActionLabel}
                </p>
                <p className="mt-1 text-sm text-slate-600">
                  Review the current blocking issues and warnings before you{" "}
                  {lifecycleActionLabel} this forecast version.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {lifecycleBlocked ? (
                  <InsightBadge label="Submit or lock blocked" tone="rose" />
                ) : (
                  <InsightBadge label="No blocking issues" tone="emerald" />
                )}
                {sanitySummary.warningChecks.length > 0 ? (
                  <InsightBadge
                    label={`${String(sanitySummary.warningChecks.length)} warning${sanitySummary.warningChecks.length === 1 ? "" : "s"} to review`}
                    tone="amber"
                  />
                ) : null}
              </div>
            </div>

            {sanitySummary.blockingChecks.length > 0 ||
            sanitySummary.otherBlockingIssues.length > 0 ? (
              <div className="mt-4 space-y-2">
                <SanityCheckList
                  checks={sanitySummary.blockingChecks}
                  lineLabelsById={lineLabelsById}
                />
                {sanitySummary.otherBlockingIssues.map((issue) => (
                  <div
                    className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-950"
                    key={`confirm:${issue}`}
                  >
                    {issue}
                  </div>
                ))}
              </div>
            ) : null}

            {sanitySummary.warningChecks.length > 0 ? (
              <div className="mt-4">
                <SanityCheckBadges checks={sanitySummary.warningChecks} maxItems={6} />
              </div>
            ) : null}

            <div className="mt-4">
              <InlineActionBar>
                <Button
                  onClick={() => setPendingLifecycleAction(null)}
                  type="button"
                  variant="ghost"
                >
                  Cancel
                </Button>
                <Button
                  disabled={
                    lifecycleBlocked ||
                    submitMutation.isPending ||
                    lockMutation.isPending
                  }
                  onClick={confirmLifecycleAction}
                  type="button"
                  variant="primary"
                >
                  {pendingLifecycleAction === "submit"
                    ? submitMutation.isPending
                      ? "Submitting..."
                      : "Confirm submit"
                    : lockMutation.isPending
                      ? "Locking..."
                      : "Confirm lock"}
                </Button>
              </InlineActionBar>
            </div>
          </div>
        ) : null}
      </SectionCard>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
        <SummaryStat
          label="Forecast total"
          value={version ? formatCurrency(version.totalAmount, currencyCode) : "Not set"}
        />
        <SummaryStat
          label="Weighted view"
          value={
            version
              ? formatCurrency(version.weightedTotalAmount, currencyCode)
              : "Not set"
          }
          hint="Commercially weighted for sales and pipeline review."
        />
        <SummaryStat
          label="Forecast range"
          value={projectRangeLabel}
          hint="Summed from monthly confidence bands."
        />
        <SummaryStat
          label="Probability"
          value={
            version ? formatPercent(version.probabilityPercent) : "Not set"
          }
          hint="Used for weighted totals."
        />
        <SummaryStat
          hint={confidenceHint}
          label="Confidence"
          tone={
            versionConfidenceChecks.length > 0
              ? "warning"
              : getConfidenceTone(version?.confidenceScore)
          }
          value={
            version?.confidenceScore != null
              ? formatPercent(version.confidenceScore)
              : "Not set"
          }
        />
        <SummaryStat
          hint={
            selectedScenarioOption
              ? `${selectedScenarioOption.count} version(s) in this scenario`
              : "No scenario summary"
          }
          label="Quote basis"
          tone={version?.isSourceQuoteCurrent ? "positive" : "warning"}
          value={version?.isSourceQuoteCurrent ? "Current quote" : "Needs rebase"}
        />
      </div>

      {versionConfidenceChecks.length > 0 ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 shadow-sm">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <p className="text-sm font-semibold text-amber-950">
                Confidence needs evidence context
              </p>
              <p className="mt-1 text-sm text-amber-900">
                Pair the confidence score with metadata completeness and data
                sufficiency before relying on it operationally.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <InsightBadge
                label={
                  version?.confidenceScore != null
                    ? `${formatPercent(version.confidenceScore)} confidence`
                    : "No confidence score"
                }
                tone="amber"
              />
              <InsightBadge
                label={
                  version?.dataSufficiencyScore != null
                    ? `${formatPercent(version.dataSufficiencyScore)} data sufficiency`
                    : "No predictive evidence linked"
                }
                tone="amber"
              />
            </div>
          </div>

          <div className="mt-4">
            <SanityCheckList checks={versionConfidenceChecks} />
          </div>
        </div>
      ) : null}

      <SectionCard
        title="Version Comparison"
        description="Review the commercial deltas between the selected version and another forecast before changing overrides."
      >
        {comparisonVersion ? (
          <>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
              <SummaryStat
                hint={`${formatStatusLabel(comparisonVersion.scenarioKey ?? "base")} scenario`}
                label="Compared version"
                value={`V${comparisonVersion.versionNumber}`}
              />
              <SummaryStat
                label="Total delta"
                value={formatCurrencyDelta(comparisonTotalDelta ?? 0, currencyCode)}
              />
              <SummaryStat
                label="Weighted delta"
                value={formatCurrencyDelta(
                  comparisonWeightedDelta ?? 0,
                  currencyCode,
                )}
              />
              <SummaryStat
                label="Probability delta"
                value={
                  comparisonProbabilityDelta != null
                    ? `${comparisonProbabilityDelta > 0 ? "+" : ""}${formatPercent(comparisonProbabilityDelta)}`
                    : "Not available"
                }
              />
              <SummaryStat
                label="Confidence delta"
                value={
                  comparisonConfidenceDelta != null
                    ? `${comparisonConfidenceDelta > 0 ? "+" : ""}${formatPercent(comparisonConfidenceDelta)}`
                    : "Not available"
                }
              />
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,0.7fr)]">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-sm font-semibold text-slate-900">
                  Changed months
                </p>
                <p className="mt-1 text-sm text-slate-600">
                  {changedComparisonRows.length > 0
                    ? `${String(changedComparisonRows.length)} month(s) differ from ${comparisonVersionLabel}.`
                    : `No month deltas against ${comparisonVersionLabel}.`}
                </p>
                {changedComparisonRows.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {changedComparisonRows.slice(0, 12).map((row) => (
                      <div
                        className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700"
                        key={row.month}
                      >
                        {formatMonthLabel(row.month)} ·{" "}
                        {formatCurrencyDelta(row.deltaAmount, currencyCode)}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-sm font-semibold text-slate-900">
                  Stored revision note
                </p>
                <p className="mt-2 text-sm text-slate-600">
                  {typeof changeSummary?.reason === "string" &&
                  changeSummary.reason.length > 0
                    ? changeSummary.reason
                    : version?.revisionReason || "No revision rationale recorded."}
                </p>
                <p className="mt-4 text-xs uppercase tracking-[0.12em] text-slate-500">
                  Engine summary
                </p>
                <p className="mt-2 text-sm text-slate-700">
                  {changedMonthCount != null
                    ? `${String(changedMonthCount)} changed month(s) persisted on this version.`
                    : "No stored change summary was persisted."}
                </p>
              </div>
            </div>

            {changedComparisonRows.length > 0 ? (
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50 text-left text-slate-600">
                    <tr>
                      <th className="px-3 py-2 font-medium">Month</th>
                      <th className="px-3 py-2 font-medium">This version</th>
                      <th className="px-3 py-2 font-medium">
                        {comparisonVersionLabel}
                      </th>
                      <th className="px-3 py-2 font-medium">Delta</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {changedComparisonRows.map((row) => (
                      <tr key={row.month}>
                        <td className="px-3 py-2 font-medium text-slate-900">
                          {formatMonthLabel(row.month)}
                        </td>
                        <td className="px-3 py-2 text-slate-700">
                          {formatCurrency(row.amount, currencyCode)}
                        </td>
                        <td className="px-3 py-2 text-slate-700">
                          {row.comparisonAmount != null
                            ? formatCurrency(row.comparisonAmount, currencyCode)
                            : "None"}
                        </td>
                        <td
                          className={cn(
                            "px-3 py-2 font-medium",
                            getDeltaTextClass(row.deltaAmount),
                          )}
                        >
                          {formatCurrencyDelta(row.deltaAmount, currencyCode)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </>
        ) : (
          <p className="text-sm text-slate-600">
            Select another version to compare this forecast against.
          </p>
        )}
      </SectionCard>

      <SectionCard
        title="Monthly View"
        description="Review timing, weighted value, confidence bands, and actual overlays month by month."
        actions={
          <SegmentedControl<MonthlyViewMode>
            onChange={setMonthlyViewMode}
            options={[
              { label: "Cards", value: "cards" },
              { label: "Table", value: "table" },
            ]}
            value={monthlyViewMode}
          />
        }
      >
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
              Months in View
            </p>
            <p className="mt-2 text-lg font-semibold text-slate-900">
              {String(monthlyRollupSummary.monthCount)}
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
              Peak Month
            </p>
            <p className="mt-2 text-lg font-semibold text-slate-900">
              {monthlyRollupSummary.peakMonth
                ? formatMonthLabel(monthlyRollupSummary.peakMonth)
                : "Not available"}
            </p>
            <p className="mt-1 text-sm text-slate-600">
              {monthlyRollupSummary.peakMonth
                ? formatCurrency(monthlyRollupSummary.peakAmount, currencyCode)
                : "No month spread yet"}
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
              Actual-Covered Months
            </p>
            <p className="mt-2 text-lg font-semibold text-slate-900">
              {String(monthlyRollupSummary.actualMonthCount)}
            </p>
            <p className="mt-1 text-sm text-slate-600">
              Posted actuals replace forecast values in these months.
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
              Months Changed vs Compare
            </p>
            <p className="mt-2 text-lg font-semibold text-slate-900">
              {String(changedComparisonRows.length)}
            </p>
            <p className="mt-1 text-sm text-slate-600">
              {comparisonVersionLabel
                ? `Against ${comparisonVersionLabel}.`
                : "Select a comparison version to populate deltas."}
            </p>
          </div>
        </div>

        {sanitySummary.affectedMonthCount > 0 ? (
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
              <div>
                <p className="text-sm font-semibold text-amber-950">
                  Flagged months
                </p>
                <p className="mt-1 text-sm text-amber-900">
                  Highlighted months carry timing, actual-assimilation, or
                  confidence concerns directly in the monthly view.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <InsightBadge
                  label={`${String(sanitySummary.affectedMonthCount)} month${sanitySummary.affectedMonthCount === 1 ? "" : "s"} flagged`}
                  tone="amber"
                />
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {Object.entries(sanitySummary.checksByMonth).map(([month, checks]) => (
                <InsightBadge
                  key={month}
                  label={`${formatMonthLabel(month)} · ${checks[0]?.title ?? "Check"}`}
                  tone={checks.some(isBlockingCheck) ? "rose" : "amber"}
                />
              ))}
            </div>
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-slate-500">
          <span className="inline-flex items-center gap-2">
            <span className="h-2 w-8 rounded-full bg-sky-200" />
            Confidence band
          </span>
          <span className="inline-flex items-center gap-2">
            <span className="h-4 w-1 rounded-full bg-slate-900" />
            Forecast amount
          </span>
          <span className="inline-flex items-center gap-2">
            <span className="h-3 w-3 rounded-full border-2 border-emerald-600 bg-white" />
            Actual amount
          </span>
          <span className="inline-flex items-center gap-2">
            <span className="h-4 w-0.5 rounded-full bg-slate-500" />
            Comparison version
          </span>
        </div>

        {monthlyComparisonRows.length === 0 ? (
          <p className="mt-4 text-sm text-slate-600">
            No monthly rollup is available yet.
          </p>
        ) : monthlyViewMode === "cards" ? (
          <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {monthlyComparisonRows.map((row) => (
              <MonthlyRollupCard
                checks={sanitySummary.checksByMonth[row.month] ?? []}
                currencyCode={currencyCode}
                key={row.month}
                maxAmount={maxMonthlyAmount}
                row={row}
                {...(comparisonVersionLabel
                  ? { comparisonVersionLabel }
                  : {})}
              />
            ))}
          </div>
        ) : (
          <div className="mt-4">
            <MonthlyComparisonTable
              checksByMonth={sanitySummary.checksByMonth}
              currencyCode={currencyCode}
              rows={monthlyComparisonRows}
              {...(comparisonVersionLabel
                ? { comparisonVersionLabel }
                : {})}
            />
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Why This Forecast"
        description="Make the delivery logic, predictive evidence, and change rationale visible before you trust the numbers."
      >
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm font-semibold text-slate-900">Methodology</p>
            <p className="mt-2 text-sm text-slate-700">{methodologySummaryText}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <InsightBadge
                label={formatStatusLabel(version?.engineSource ?? "unified_forecast_engine")}
                tone="sky"
              />
              <InsightBadge
                label={formatStatusLabel(version?.scenarioKey ?? "base")}
                tone="slate"
              />
              {version?.fallbackTier ? (
                <InsightBadge
                  label={`Fallback ${formatStatusLabel(version.fallbackTier)}`}
                  tone="amber"
                />
              ) : null}
              {projectFormatKey ? (
                <InsightBadge
                  label={`Format ${formatStatusLabel(projectFormatKey)}`}
                  tone="slate"
                />
              ) : null}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
              <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
                Prediction Run
              </p>
              <p className="mt-2 text-sm font-semibold text-slate-900">
                {version?.predictionRunId
                  ? version.predictionRunId.slice(0, 8)
                  : "Not linked"}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {version?.predictionScenarioKey
                  ? `${formatStatusLabel(version.predictionScenarioKey)} scenario`
                  : "No predictive scenario linked"}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
              <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
                Actual Months
              </p>
              <p className="mt-2 text-sm font-semibold text-slate-900">
                {String(actualMonthCount)}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Months already replaced by posted actual revenue.
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
              <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
                Stored Delta
              </p>
              <p className="mt-2 text-sm font-semibold text-slate-900">
                {changeSummary?.totalAmountDelta != null
                  ? formatCurrency(
                      Number(changeSummary.totalAmountDelta),
                      currencyCode,
                    )
                  : "Not available"}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {changedMonthCount != null
                  ? `${String(changedMonthCount)} changed month(s)`
                  : "No prior version delta stored"}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
              <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
                Source Quote
              </p>
              <p className="mt-2 text-sm font-semibold text-slate-900">
                {version?.sourceQuoteVersionId ?? "Not linked"}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {version?.isSourceQuoteCurrent ? "Current quote basis" : "Stale against current quote"}
              </p>
            </div>
          </div>
        </div>

        {changedMonths.length > 0 ? (
          <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
            <p className="text-sm font-semibold text-slate-900">
              Engine-flagged changed months
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {changedMonths.map((month) => (
                <span
                  className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700"
                  key={month}
                >
                  {formatMonthLabel(month)}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {explanationCards.length > 0 ? (
            explanationCards.slice(0, 9).map(({ explanation, line }) => (
              <div
                className="rounded-xl border border-slate-200 bg-white p-4"
                key={`${line.id}:${explanation.key}`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold text-slate-900">
                    {explanation.label}
                  </p>
                  <InsightBadge
                    label={formatStatusLabel(explanation.impact)}
                    tone={
                      explanation.impact.toLowerCase().includes("actual")
                        ? "emerald"
                        : "sky"
                    }
                  />
                </div>
                <p className="mt-2 text-sm text-slate-600">{line.label}</p>
                <p className="mt-3 text-sm text-slate-700">
                  {explanation.detail}
                </p>
              </div>
            ))
          ) : (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              No line-level explanations were persisted for this version.
            </div>
          )}
        </div>
      </SectionCard>

      <SectionCard
        title="Version Metadata"
        description="Keep the commercial framing and audit rationale aligned with the working forecast."
        actions={
          <Button
            disabled={!isDraftVersion || updateVersionMutation.isPending}
            onClick={() => updateVersionMutation.mutate()}
            type="button"
            variant="primary"
          >
            {updateVersionMutation.isPending ? "Saving..." : "Save metadata"}
          </Button>
        }
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
              version?.outcomeTypeSnapshot === "awarded" ||
              version?.outcomeTypeSnapshot === "lost"
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
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
            <p className="font-medium text-slate-900">Outcome bucket</p>
            <p className="mt-1">
              {formatStatusLabel(version?.outcomeTypeSnapshot ?? "unknown")}
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
            <p className="font-medium text-slate-900">Scenario</p>
            <p className="mt-1">
              {formatStatusLabel(version?.scenarioKey ?? "base")}
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
            <p className="font-medium text-slate-900">Created</p>
            <p className="mt-1">{formatDateTime(version?.createdAt)}</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
            <p className="font-medium text-slate-900">Updated</p>
            <p className="mt-1">{formatDateTime(version?.updatedAt)}</p>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Line Planning"
        description="Review exceptions first, then adjust the base line planning mode. Use Revenue Phasing for month-by-month manual overrides."
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <SummaryStat label="Fully manual lines" value={String(manualLineCount)} />
          <SummaryStat label="System-generated lines" value={String(scheduleLineCount)} />
          <SummaryStat
            label="Lines flagged"
            tone={attentionLineCount > 0 ? "warning" : "default"}
            value={String(attentionLineCount)}
          />
          <SummaryStat
            label="Actual-backed lines"
            value={String(actualBackedLineCount)}
          />
        </div>

        <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
          <p className="font-medium text-slate-900">Operator flow</p>
          <p className="mt-2">
            1. Review issues and explanations. 2. Choose the base line planning mode. 3. Record
            the rationale for the change. 4. Save the line so audit history and recalculation
            behaviour stay traceable.
          </p>
          <p className="mt-2">
            Month-by-month operator overrides now belong in{" "}
            <Link className="font-medium text-slate-900 underline" href={`/projects/phasing?projectId=${projectId}`}>
              Revenue Phasing
            </Link>
            , so the monthly spreadsheet and dashboard both read from one phasing model.
          </p>
        </div>

        <div className="mt-6 space-y-4">
          {sortedLines.map((line) => {
            const draft = lineDrafts[line.id] ?? buildLineDraft(line);
            const lineChecks = line.sanityChecks ?? [];
            const lineConfidenceChecks = lineChecks.filter((check) =>
              ["confidence_too_high_for_metadata", "narrow_bands_sparse_data"].includes(
                check.key,
              ),
            );
            const scheduleOptions = getScheduleRangeOptions(
              line,
              projectScheduleRanges,
            );
            const inputSummary = summarizeForecastInputs(
              (line.forecastInputs as Record<string, unknown> | null | undefined) ??
                null,
            );
            const manualDraftTotal =
              draft.allocationMethod === "manual"
                ? sumDraftAllocations(draft.allocations)
                : null;
            const manualDraftDelta =
              manualDraftTotal != null
                ? roundAmount(manualDraftTotal - line.totalAmount)
                : null;

            return (
              <div
                className={cn(
                  "space-y-4 rounded-xl border p-4 shadow-sm",
                  getSanitySurfaceClass(lineChecks),
                )}
                key={line.id}
              >
                <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-base font-semibold text-slate-900">
                        {line.label}
                      </p>
                      <InsightBadge
                        label={
                          draft.allocationMethod === "manual"
                            ? "Manual override"
                            : "Schedule driven"
                        }
                        tone={
                          draft.allocationMethod === "manual" ? "amber" : "sky"
                        }
                      />
                      {line.issues.length > 0 ? (
                        <InsightBadge
                          label={`${String(line.issues.length)} issue${line.issues.length === 1 ? "" : "s"}`}
                          tone="rose"
                        />
                      ) : null}
                      {lineChecks.length > 0 ? (
                        <InsightBadge
                          label={`${String(lineChecks.length)} sanity check${lineChecks.length === 1 ? "" : "s"}`}
                          tone={lineChecks.some(isBlockingCheck) ? "rose" : "amber"}
                        />
                      ) : null}
                      {(line.actualsToDateAmount ?? 0) > 0 ? (
                        <InsightBadge label="Actuals posted" tone="emerald" />
                      ) : null}
                      <SanityCheckBadges checks={lineChecks} maxItems={2} />
                    </div>

                    <p className="text-sm text-slate-600">
                      {formatCurrency(line.totalAmount, line.currencyCode)} total ·{" "}
                      {formatCurrency(
                        line.weightedTotalAmount,
                        line.currencyCode,
                      )}{" "}
                      weighted
                    </p>

                    <p className="text-xs text-slate-500">
                      Source line: {line.sourceLineId} · Method{" "}
                      {formatStatusLabel(
                        line.forecastMethodKey ?? line.allocationMethod,
                      )}{" "}
                      · Profile{" "}
                      {formatStatusLabel(line.allocationProfileKey ?? "even")}
                      {inputSummary ? ` · ${inputSummary}` : ""}
                    </p>
                  </div>

                  <div className="space-y-2">
                    <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
                      Allocation mode
                    </p>
                    <SegmentedControl<AllocationMethod>
                      disabled={!isDraftVersion}
                      onChange={(value) =>
                        setLineDrafts((current) => {
                          const currentDraft =
                            current[line.id] ?? buildLineDraft(line);

                          return {
                            ...current,
                            [line.id]: {
                              ...currentDraft,
                              allocationMethod: value,
                              allocations:
                                value === "manual" &&
                                currentDraft.allocations.length === 0
                                  ? buildLineDraft(line).allocations
                                  : currentDraft.allocations,
                            },
                          };
                        })
                      }
                      options={[
                        { label: "Schedule", value: "schedule" },
                        { label: "Manual", value: "manual" },
                      ]}
                      value={draft.allocationMethod}
                    />
                  </div>
                </div>

                {line.issues.length > 0 ? (
                  <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">
                    {line.issues.join(", ")}
                  </div>
                ) : null}

                {lineChecks.length > 0 ? (
                  <SanityCheckList checks={lineChecks} lineLabelsById={lineLabelsById} />
                ) : null}

                {line.notes ? (
                  <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                    {line.notes}
                  </div>
                ) : null}

                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                  <div
                    className={cn(
                      "rounded-xl border bg-slate-50 px-4 py-3 text-sm text-slate-700",
                      lineConfidenceChecks.length > 0
                        ? "border-amber-300"
                        : "border-slate-200",
                    )}
                  >
                    <p className="font-medium text-slate-900">Confidence</p>
                    <p className="mt-1">
                      {line.confidenceScore != null
                        ? formatPercent(line.confidenceScore)
                        : "Not available"}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {getConfidenceLabel(line.confidenceScore)}
                    </p>
                  </div>
                  <div
                    className={cn(
                      "rounded-xl border bg-slate-50 px-4 py-3 text-sm text-slate-700",
                      lineConfidenceChecks.length > 0
                        ? "border-amber-300"
                        : "border-slate-200",
                    )}
                  >
                    <p className="font-medium text-slate-900">Data sufficiency</p>
                    <p className="mt-1">
                      {line.dataSufficiencyScore != null
                        ? formatPercent(line.dataSufficiencyScore)
                        : "Not available"}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {line.fallbackTier
                        ? `Fallback ${formatStatusLabel(line.fallbackTier)}`
                        : "No fallback recorded"}
                    </p>
                    {lineConfidenceChecks.length > 0 ? (
                      <p className="mt-2 text-xs text-amber-700">
                        Review this line’s confidence together with its data
                        sufficiency and band width warnings.
                      </p>
                    ) : null}
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                    <p className="font-medium text-slate-900">Actuals to date</p>
                    <p className="mt-1">
                      {line.actualsToDateAmount != null
                        ? formatCurrency(
                            line.actualsToDateAmount,
                            line.currencyCode,
                          )
                        : "None"}
                    </p>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                    <p className="font-medium text-slate-900">Remaining amount</p>
                    <p className="mt-1">
                      {line.remainingAmount != null
                        ? formatCurrency(line.remainingAmount, line.currencyCode)
                        : "Not available"}
                    </p>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                    <p className="font-medium text-slate-900">Sequence stage</p>
                    <p className="mt-1">
                      {line.sequencingStageKey
                        ? formatStatusLabel(line.sequencingStageKey)
                        : "Full timeline"}
                    </p>
                    {line.overlapPercent != null ? (
                      <p className="mt-1 text-xs text-slate-500">
                        {line.overlapPercent}% overlap
                      </p>
                    ) : null}
                  </div>
                </div>

                {line.explanations.length > 0 ? (
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {line.explanations.map((explanation) => (
                      <div
                        className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700"
                        key={`${line.id}:${explanation.key}`}
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-medium text-slate-900">
                            {explanation.label}
                          </p>
                          <InsightBadge
                            label={formatStatusLabel(explanation.impact)}
                            tone="sky"
                          />
                        </div>
                        <p className="mt-2">{explanation.detail}</p>
                      </div>
                    ))}
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
                            scheduleRangeId: event.target.value,
                          },
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

                    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                      Schedule-driven lines recalculate from project schedule
                      ranges. Use a specific range when ops needs to pin the work
                      to a delivery window, then save the line so the override is
                      traceable.
                    </div>

                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                      {line.allocations.map((allocation) => {
                        const allocationChecks = lineChecks.filter(
                          (check) => check.month === allocation.month,
                        );

                        return (
                          <div
                            className={cn(
                              "rounded-xl border px-4 py-3",
                              getSanitySurfaceClass(allocationChecks),
                            )}
                            key={`${line.id}:${allocation.month}`}
                          >
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-sm font-medium text-slate-900">
                                {formatMonthLabel(allocation.month)}
                              </p>
                              <div className="flex flex-wrap justify-end gap-2">
                                <InsightBadge
                                  label={formatStatusLabel(
                                    allocation.allocationSource ?? "forecast",
                                  )}
                                  tone={
                                    allocation.allocationSource === "actual"
                                      ? "emerald"
                                      : allocation.allocationSource === "manual_override"
                                        ? "amber"
                                        : "sky"
                                  }
                                />
                                <SanityCheckBadges
                                  checks={allocationChecks}
                                  maxItems={1}
                                />
                              </div>
                            </div>
                            <p className="mt-2 text-sm font-medium text-slate-900">
                              {formatCurrency(
                                allocation.amount,
                                line.currencyCode,
                              )}
                            </p>
                            <p className="mt-1 text-xs text-slate-500">
                              Weighted{" "}
                              {formatCurrency(
                                allocation.weightedAmount,
                                line.currencyCode,
                              )}
                            </p>
                            <p className="mt-1 text-xs text-slate-500">
                              Band{" "}
                              {formatAmountRange(
                                allocation.lowAmount,
                                allocation.highAmount,
                                line.currencyCode,
                              )}
                            </p>
                            {allocation.actualAmount != null ? (
                              <p className="mt-1 text-xs text-slate-500">
                                Actual{" "}
                                {formatCurrency(
                                  allocation.actualAmount,
                                  line.currencyCode,
                                )}
                              </p>
                            ) : null}
                            {allocationChecks.length > 0 ? (
                              <p
                                className={cn(
                                  "mt-2 text-xs",
                                  allocationChecks.some(isBlockingCheck)
                                    ? "text-rose-800"
                                    : "text-amber-800",
                                )}
                              >
                                {allocationChecks[0]?.detail}
                              </p>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  </>
                ) : (
                  <div className="space-y-4">
                    <div className="grid gap-3 md:grid-cols-3">
                      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                        <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
                          Draft total
                        </p>
                        <p className="mt-2 text-sm font-semibold text-slate-900">
                          {manualDraftTotal != null
                            ? formatCurrency(manualDraftTotal, line.currencyCode)
                            : "Not set"}
                        </p>
                      </div>
                      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                        <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
                          Line total
                        </p>
                        <p className="mt-2 text-sm font-semibold text-slate-900">
                          {formatCurrency(line.totalAmount, line.currencyCode)}
                        </p>
                      </div>
                      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                        <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
                          Difference
                        </p>
                        <p
                          className={cn(
                            "mt-2 text-sm font-semibold",
                            getDeltaTextClass(manualDraftDelta ?? 0),
                          )}
                        >
                          {manualDraftDelta != null
                            ? formatCurrencyDelta(
                                manualDraftDelta,
                                line.currencyCode,
                              )
                            : "Not available"}
                        </p>
                      </div>
                    </div>

                    {manualDraftDelta != null && Math.abs(manualDraftDelta) > 0.009 ? (
                      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                        The manual month plan is{" "}
                        {manualDraftDelta > 0 ? "over" : "under"} the line total by{" "}
                        {formatCurrency(Math.abs(manualDraftDelta), line.currencyCode)}.
                        Save only when that difference is intentional.
                      </div>
                    ) : null}

                    {draft.allocations.map((allocation) => {
                      const allocationChecks = lineChecks.filter(
                        (check) => check.month === allocation.month,
                      );

                      return (
                        <div
                          className={cn(
                            "grid gap-3 rounded-xl border p-4 md:grid-cols-[180px_minmax(0,1fr)_auto]",
                            allocationChecks.some(isBlockingCheck)
                              ? "border-rose-300 bg-rose-50/50"
                              : allocationChecks.length > 0
                                ? "border-amber-300 bg-amber-50/50"
                                : "border-slate-200 bg-slate-50",
                          )}
                          key={allocation.id}
                        >
                          <TextInput
                            disabled={!isDraftVersion}
                            label="Month"
                            onChange={(event) =>
                              setLineDrafts((current) => ({
                                ...current,
                                [line.id]: {
                                  ...(current[line.id] ?? buildLineDraft(line)),
                                  allocations: (
                                    current[line.id]?.allocations ??
                                    buildLineDraft(line).allocations
                                  ).map((item) =>
                                    item.id === allocation.id
                                      ? { ...item, month: event.target.value }
                                      : item,
                                  ),
                                },
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
                                  allocations: (
                                    current[line.id]?.allocations ??
                                    buildLineDraft(line).allocations
                                  ).map((item) =>
                                    item.id === allocation.id
                                      ? {
                                          ...item,
                                          amount: event.target.value,
                                        }
                                      : item,
                                  ),
                                },
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
                                      current[line.id]?.allocations ??
                                      buildLineDraft(line).allocations
                                    ).filter((item) => item.id !== allocation.id),
                                  },
                                }))
                              }
                              type="button"
                              variant="ghost"
                            >
                              Remove
                            </Button>
                          </div>
                          {allocationChecks.length > 0 ? (
                            <div className="md:col-span-3">
                              <SanityCheckBadges checks={allocationChecks} maxItems={2} />
                              <p
                                className={cn(
                                  "mt-2 text-xs",
                                  allocationChecks.some(isBlockingCheck)
                                    ? "text-rose-800"
                                    : "text-amber-800",
                                )}
                              >
                                {allocationChecks[0]?.detail}
                              </p>
                            </div>
                          ) : null}
                        </div>
                      );
                    })}

                    <Button
                      disabled={!isDraftVersion}
                      onClick={() =>
                        setLineDrafts((current) => {
                          const currentDraft = current[line.id] ?? buildLineDraft(line);
                          const lastMonth =
                            currentDraft.allocations[currentDraft.allocations.length - 1]
                              ?.month;

                          return {
                            ...current,
                            [line.id]: {
                              ...currentDraft,
                              allocations: [
                                ...currentDraft.allocations,
                                {
                                  id: buildAllocationId(
                                    line.id,
                                    currentDraft.allocations.length,
                                  ),
                                  month: nextMonth(lastMonth),
                                  amount: "0",
                                },
                              ],
                            },
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
                  label="Override reason / audit note"
                  onChange={(event) =>
                    setLineDrafts((current) => ({
                      ...current,
                      [line.id]: {
                        ...(current[line.id] ?? buildLineDraft(line)),
                        reason: event.target.value,
                      },
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
                    {lineMutation.isPending && lineMutation.variables === line.id
                      ? "Saving line..."
                      : "Save line"}
                  </Button>
                </InlineActionBar>
              </div>
            );
          })}
        </div>
      </SectionCard>

      <SectionCard
        title="Policy Reference"
        description="Reference the active timing assumptions without losing the working context above."
      >
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="space-y-3">
            <div>
              <p className="text-sm font-medium text-slate-900">Curve profiles</p>
              <p className="text-xs text-slate-500">
                Revenue spread shapes available before fallback logic is used.
              </p>
            </div>
            {policyQuery.data.curveProfiles?.length ? (
              policyQuery.data.curveProfiles.map((profile) => (
                <div
                  className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
                  key={profile.key}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-slate-900">
                      {profile.label}
                    </p>
                    <InsightBadge
                      label={formatStatusLabel(profile.shapeKey)}
                      tone="sky"
                    />
                  </div>
                  <p className="mt-2 text-sm text-slate-600">
                    {profile.description ?? "No profile description recorded."}
                  </p>
                  <p className="mt-2 text-xs text-slate-500">
                    Default disciplines:{" "}
                    {(profile.defaultForDisciplines ?? []).length > 0
                      ? (profile.defaultForDisciplines ?? [])
                          .map((item) => formatStatusLabel(item))
                          .join(", ")
                      : "None"}
                  </p>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-600">
                No curve profiles are configured.
              </p>
            )}
          </div>

          <div className="space-y-3">
            <div>
              <p className="text-sm font-medium text-slate-900">
                Sequencing templates
              </p>
              <p className="text-xs text-slate-500">
                Discipline timing windows and overlap assumptions that shape monthly timing.
              </p>
            </div>
            {policyQuery.data.sequencingTemplates?.length ? (
              policyQuery.data.sequencingTemplates.map((template) => (
                <div
                  className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
                  key={template.key}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-slate-900">
                      {template.label}
                    </p>
                    <InsightBadge
                      label={`${String((template.stages ?? []).length)} stage${(template.stages ?? []).length === 1 ? "" : "s"}`}
                      tone="slate"
                    />
                  </div>
                  <p className="mt-2 text-xs text-slate-500">
                    Project formats:{" "}
                    {(template.projectFormatKeys ?? []).length > 0
                      ? (template.projectFormatKeys ?? [])
                          .map((item) => formatStatusLabel(item))
                          .join(", ")
                      : "Default fallback"}
                  </p>
                  <div className="mt-3 space-y-2">
                    {(template.stages ?? []).slice(0, 4).map((stage) => (
                      <div
                        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600"
                        key={`${template.key}-${stage.disciplineCode}`}
                      >
                        <span className="font-medium text-slate-900">
                          {formatStatusLabel(stage.disciplineCode)}
                        </span>{" "}
                        {"->"} {formatStatusLabel(stage.stageKey)} ·{" "}
                        {Math.round(stage.startPct * 100)}% to{" "}
                        {Math.round(stage.endPct * 100)}%
                        {stage.overlapPct != null
                          ? ` · ${stage.overlapPct}% overlap`
                          : ""}
                      </div>
                    ))}
                    {(template.stages ?? []).length > 4 ? (
                      <p className="text-xs text-slate-500">
                        +{(template.stages ?? []).length - 4} more stage
                        {(template.stages ?? []).length - 4 === 1 ? "" : "s"}
                      </p>
                    ) : null}
                  </div>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-600">
                No sequencing templates are configured.
              </p>
            )}
          </div>
        </div>

        <p className="mt-4 text-sm text-slate-600">
          Profiles: {summarizePolicyLabels(policyQuery.data.curveProfiles ?? [])}.
          Sequences:{" "}
          {summarizePolicyLabels(policyQuery.data.sequencingTemplates ?? [])}.
        </p>
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
                <div
                  className="rounded-lg border border-slate-200 px-4 py-3"
                  key={event.id}
                >
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-sm font-medium text-slate-900">
                      {describeAuditEvent(event)}
                    </p>
                    <p className="text-xs text-slate-500">
                      {formatDateTime(event.createdAt)}
                    </p>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {event.action} · {event.actorEmail ?? "System"}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-600">
              No audit events are available for this project yet.
            </p>
          )}
        </SectionCard>
      ) : null}
    </div>
  );
}
