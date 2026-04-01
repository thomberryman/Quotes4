"use client";

import type {
  AwardedLostMonthPoint,
  DisciplineRevenueSeries,
  PipelineStageSummary,
  RevenueMonthPoint,
  VarianceBucketSummary,
} from "@quotes4/contracts";

import { formatCurrency, formatPercent } from "@/lib/format";

import { formatDashboardMonth } from "./dashboard-helpers";

const disciplineColors = [
  "bg-slate-900",
  "bg-sky-500",
  "bg-emerald-500",
  "bg-amber-500",
  "bg-rose-500",
  "bg-indigo-500",
];

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
): string {
  return getCoordinates(values, width, height, paddingX, paddingY)
    .map((point) => `${point.x},${point.y}`)
    .join(" ");
}

export function PipelineChart({
  currencyCode,
  stages,
}: {
  currencyCode: string;
  stages: PipelineStageSummary[];
}) {
  const maxQuote = getMaxValue(stages.map((stage) => stage.quoteAmount));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 text-xs text-slate-500">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-slate-900" />
          Weighted value
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-slate-300" />
          Unweighted remainder
        </div>
      </div>
      <div className="space-y-3">
        {stages.map((stage) => {
          const stageWidth = `${(stage.quoteAmount / maxQuote) * 100}%`;
          const weightedShare =
            stage.quoteAmount > 0
              ? Math.min(100, (stage.weightedAmount / stage.quoteAmount) * 100)
              : 0;

          return (
            <div className="space-y-1.5" key={stage.status}>
              <div className="flex items-center justify-between gap-3 text-sm">
                <div>
                  <p className="font-medium text-slate-900">
                    {stage.label}
                    <span className="ml-2 text-slate-500">
                      {stage.projectCount} projects
                    </span>
                  </p>
                </div>
                <p className="text-right text-slate-600">
                  {formatCurrency(stage.quoteAmount, currencyCode)}
                </p>
              </div>
              <div className="h-3 rounded-full bg-slate-100">
                <div
                  className="flex h-full overflow-hidden rounded-full"
                  style={{ width: stageWidth }}
                >
                  <div
                    className="bg-slate-900"
                    style={{ width: `${weightedShare}%` }}
                  />
                  <div
                    className="bg-slate-300"
                    style={{ width: `${100 - weightedShare}%` }}
                  />
                </div>
              </div>
              <div className="flex items-center justify-between gap-3 text-xs text-slate-500">
                <span>
                  Weighted {formatCurrency(stage.weightedAmount, currencyCode)}
                </span>
                <span>
                  Booked {formatCurrency(stage.bookedAmount, currencyCode)}
                </span>
                <span>
                  Remaining{" "}
                  {formatCurrency(
                    Math.max(stage.quoteAmount - stage.weightedAmount, 0),
                    currencyCode,
                  )}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function RevenueLineChart({
  currencyCode,
  months,
}: {
  currencyCode: string;
  months: RevenueMonthPoint[];
}) {
  const width = 720;
  const height = 220;
  const paddingX = 36;
  const paddingY = 22;
  const grossValues = months.map((month) => month.grossAmount);
  const weightedValues = months.map((month) => month.weightedAmount);
  const lowValues = months.map((month) => month.lowAmount ?? month.grossAmount);
  const highValues = months.map((month) => month.highAmount ?? month.grossAmount);
  const actualValues = months.map((month) => month.actualAmount ?? 0);
  const hasActuals = actualValues.some((value) => value > 0);
  const maxValue = getMaxValue([
    ...grossValues,
    ...weightedValues,
    ...highValues,
    ...actualValues,
  ]);
  const grossPoints = getLinePoints(grossValues, width, height, paddingX, paddingY);
  const weightedPoints = getLinePoints(
    weightedValues,
    width,
    height,
    paddingX,
    paddingY,
  );
  const actualPoints = getLinePoints(actualValues, width, height, paddingX, paddingY);
  const lowCoordinates = getCoordinates(lowValues, width, height, paddingX, paddingY);
  const highCoordinates = getCoordinates(highValues, width, height, paddingX, paddingY);
  const confidenceBandPoints = [
    ...highCoordinates.map((point) => `${point.x},${point.y}`),
    ...lowCoordinates.reverse().map((point) => `${point.x},${point.y}`),
  ].join(" ");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 text-xs text-slate-500">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-sky-100" />
          Expected range
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-sky-500" />
          Gross forecast
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-slate-900" />
          Weighted forecast
        </div>
        {hasActuals ? (
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
            Actuals posted
          </div>
        ) : null}
      </div>
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
        <svg
          aria-label="Monthly revenue forecast chart"
          className="h-auto w-full"
          viewBox={`0 0 ${width} ${height}`}
        >
          {[0, 0.5, 1].map((tick) => {
            const y = height - paddingY - tick * (height - paddingY * 2);
            const labelValue = maxValue * tick;

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
                  {formatCurrency(labelValue, currencyCode)}
                </text>
              </g>
            );
          })}

          <polygon
            fill="#e0f2fe"
            opacity="0.7"
            points={confidenceBandPoints}
          />
          <polyline
            fill="none"
            points={grossPoints}
            stroke="#0ea5e9"
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeWidth="3"
          />
          <polyline
            fill="none"
            points={weightedPoints}
            stroke="#0f172a"
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeWidth="3"
          />
          {hasActuals ? (
            <polyline
              fill="none"
              points={actualPoints}
              stroke="#10b981"
              strokeDasharray="6 4"
              strokeLinejoin="round"
              strokeLinecap="round"
              strokeWidth="3"
            />
          ) : null}

          {months.map((month, index) => {
            const x =
              months.length === 1
                ? width / 2
                : paddingX +
                  ((width - paddingX * 2) / (months.length - 1)) * index;
            const grossY =
              height -
              paddingY -
              (month.grossAmount / maxValue) * (height - paddingY * 2);
            const weightedY =
              height -
              paddingY -
              (month.weightedAmount / maxValue) * (height - paddingY * 2);
            const actualY =
              height -
              paddingY -
              ((month.actualAmount ?? 0) / maxValue) * (height - paddingY * 2);

            return (
              <g key={month.month}>
                <circle cx={x} cy={grossY} fill="#0ea5e9" r="4" />
                <circle cx={x} cy={weightedY} fill="#0f172a" r="4" />
                {(month.actualAmount ?? 0) > 0 ? (
                  <circle cx={x} cy={actualY} fill="#10b981" r="4" />
                ) : null}
              </g>
            );
          })}
        </svg>
        <div className="mt-3 grid gap-2 text-xs text-slate-500 md:grid-cols-4">
          {months.map((month) => (
            <div key={month.month}>
              <p className="font-medium text-slate-700">
                {formatDashboardMonth(month.month)}
              </p>
              <p>Gross {formatCurrency(month.grossAmount, currencyCode)}</p>
              <p>Weighted {formatCurrency(month.weightedAmount, currencyCode)}</p>
              <p>
                Range{" "}
                {formatCurrency(month.lowAmount ?? month.grossAmount, currencyCode)} to{" "}
                {formatCurrency(month.highAmount ?? month.grossAmount, currencyCode)}
              </p>
              {(month.actualAmount ?? 0) > 0 ? (
                <p>Actual {formatCurrency(month.actualAmount ?? 0, currencyCode)}</p>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function AwardedLostChart({
  currencyCode,
  months,
}: {
  currencyCode: string;
  months: AwardedLostMonthPoint[];
}) {
  const maxCount = getMaxValue(
    months.flatMap((month) => [month.awardedCount, month.lostCount]),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 text-xs text-slate-500">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
          Awarded count
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
          Lost count
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {months.map((month) => {
          const awardedHeight =
            month.awardedCount === 0 ? 0 : Math.max(16, (month.awardedCount / maxCount) * 96);
          const lostHeight =
            month.lostCount === 0 ? 0 : Math.max(16, (month.lostCount / maxCount) * 96);

          return (
            <div
              className="rounded-xl border border-slate-200 bg-slate-50 p-4"
              key={month.month}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="font-medium text-slate-900">
                  {formatDashboardMonth(month.month)}
                </p>
                <p className="text-xs text-slate-500">
                  Total{" "}
                  {formatCurrency(
                    month.awardedAmount + month.lostAmount,
                    currencyCode,
                  )}
                </p>
              </div>
              <div className="mt-4 flex h-28 items-end gap-4">
                <div className="flex flex-1 flex-col items-center gap-2">
                  <div className="text-xs font-medium text-slate-600">
                    {month.awardedCount}
                  </div>
                  <div
                    className="w-full rounded-t-md bg-emerald-500"
                    style={{ height: `${awardedHeight}px` }}
                  />
                </div>
                <div className="flex flex-1 flex-col items-center gap-2">
                  <div className="text-xs font-medium text-slate-600">
                    {month.lostCount}
                  </div>
                  <div
                    className="w-full rounded-t-md bg-rose-500"
                    style={{ height: `${lostHeight}px` }}
                  />
                </div>
              </div>
              <div className="mt-3 grid gap-1 text-xs text-slate-500">
                <p>Awarded {formatCurrency(month.awardedAmount, currencyCode)}</p>
                <p>Lost {formatCurrency(month.lostAmount, currencyCode)}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function VarianceDivergingChart({
  currencyCode,
  buckets,
}: {
  currencyCode: string;
  buckets: VarianceBucketSummary[];
}) {
  const maxVariance = getMaxValue(
    buckets.map((bucket) => Math.abs(bucket.varianceAmount)),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 text-xs text-slate-500">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
          Under quote
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-slate-400" />
          On target
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
          Over quote
        </div>
      </div>
      <div className="space-y-3">
        {buckets.map((bucket) => {
          const width = `${(Math.abs(bucket.varianceAmount) / maxVariance) * 50}%`;
          const tone =
            bucket.key === "on_target"
              ? "bg-slate-400"
              : bucket.varianceAmount < 0
                ? "bg-emerald-500"
                : "bg-rose-500";

          return (
            <div className="space-y-1.5" key={bucket.key}>
              <div className="flex items-center justify-between gap-3 text-sm">
                <div>
                  <p className="font-medium text-slate-900">{bucket.label}</p>
                  <p className="text-xs text-slate-500">
                    {bucket.projectCount} projects
                  </p>
                </div>
                <p className="text-right text-slate-600">
                  {formatCurrency(bucket.varianceAmount, currencyCode)}
                </p>
              </div>
              <div className="relative h-4 rounded-full bg-slate-100">
                <div className="absolute inset-y-0 left-1/2 w-px bg-slate-300" />
                <div
                  className={`${tone} absolute inset-y-0 rounded-full`}
                  style={
                    bucket.varianceAmount < 0
                      ? { right: "50%", width }
                      : { left: "50%", width }
                  }
                />
              </div>
              <div className="flex items-center justify-between gap-3 text-xs text-slate-500">
                <span>Quote {formatCurrency(bucket.quotedAmount, currencyCode)}</span>
                <span>Actual {formatCurrency(bucket.actualAmount, currencyCode)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function DisciplineStackedChart({
  currencyCode,
  months,
  series,
}: {
  currencyCode: string;
  months: string[];
  series: DisciplineRevenueSeries[];
}) {
  const maxTotal = getMaxValue(
    months.map((month) =>
      series.reduce((sum, item) => {
        const point = item.points.find((candidate) => candidate.month === month);
        return sum + (point?.weightedAmount ?? 0);
      }, 0),
    ),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 text-xs text-slate-500">
        {series.map((item, index) => (
          <div className="flex items-center gap-2" key={item.disciplineId}>
            <span
              className={`h-2.5 w-2.5 rounded-full ${disciplineColors[index % disciplineColors.length]}`}
            />
            {item.disciplineName}
          </div>
        ))}
      </div>
      <div className="space-y-3">
        {months.map((month) => {
          const items = series.map((item, index) => {
            const point = item.points.find((candidate) => candidate.month === month);
            return {
              disciplineId: item.disciplineId,
              disciplineName: item.disciplineName,
              grossAmount: point?.grossAmount ?? 0,
              weightedAmount: point?.weightedAmount ?? 0,
              color: disciplineColors[index % disciplineColors.length],
            };
          });
          const monthTotal = items.reduce(
            (sum, item) => sum + item.weightedAmount,
            0,
          );
          const rowWidth = `${(monthTotal / maxTotal) * 100}%`;

          return (
            <div className="space-y-1.5" key={month}>
              <div className="flex items-center justify-between gap-3 text-sm">
                <p className="font-medium text-slate-900">
                  {formatDashboardMonth(month)}
                </p>
                <p className="text-right text-slate-600">
                  Weighted {formatCurrency(monthTotal, currencyCode)}
                </p>
              </div>
              <div className="h-4 rounded-full bg-slate-100">
                <div
                  className="flex h-full overflow-hidden rounded-full"
                  style={{ width: rowWidth }}
                >
                  {items.map((item) => {
                    if (item.weightedAmount <= 0 || monthTotal <= 0) {
                      return null;
                    }

                    return (
                      <div
                        className={item.color}
                        key={`${month}-${item.disciplineId}`}
                        style={{
                          width: `${(item.weightedAmount / monthTotal) * 100}%`,
                        }}
                      />
                    );
                  })}
                </div>
              </div>
              <div className="grid gap-1 text-xs text-slate-500 md:grid-cols-3">
                {items
                  .filter((item) => item.weightedAmount > 0)
                  .map((item) => (
                    <p key={`${month}-${item.disciplineId}-label`}>
                      {item.disciplineName}{" "}
                      <span className="font-medium text-slate-700">
                        {formatCurrency(item.weightedAmount, currencyCode)}
                      </span>
                    </p>
                  ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ConfidenceBandCards({
  averageScore,
  bands,
  highConfidenceCount,
  projectCount,
}: {
  averageScore: number;
  bands: Array<{ band: string; label: string; projectCount: number }>;
  highConfidenceCount: number;
  projectCount: number;
}) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Average confidence
          </p>
          <p className="mt-2 text-3xl font-semibold text-slate-900">
            {averageScore.toFixed(1)}
          </p>
          <p className="mt-2 text-sm text-slate-600">
            Derived from probability, status, actuals coverage, and issue load.
          </p>
        </div>
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-emerald-700">
            High confidence
          </p>
          <p className="mt-2 text-3xl font-semibold text-emerald-900">
            {highConfidenceCount}
          </p>
          <p className="mt-2 text-sm text-emerald-800">
            {projectCount} total projects currently in scope.
          </p>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {bands.map((band) => (
          <div
            className="rounded-xl border border-slate-200 bg-white p-4"
            key={band.band}
          >
            <div className="flex items-center justify-between gap-3">
              <p className="font-medium text-slate-900">{band.label}</p>
              <p className="text-sm text-slate-500">{band.projectCount}</p>
            </div>
            <div className="mt-3 h-2 rounded-full bg-slate-100">
              <div
                className={
                  band.band === "high"
                    ? "h-full rounded-full bg-emerald-500"
                    : band.band === "medium"
                      ? "h-full rounded-full bg-amber-500"
                      : "h-full rounded-full bg-slate-500"
                }
                style={{
                  width: `${projectCount > 0 ? (band.projectCount / projectCount) * 100 : 0}%`,
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function BenchmarkBandList({
  buckets,
  currencyCode,
}: {
  buckets: VarianceBucketSummary[];
  currencyCode: string;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {buckets.map((bucket) => (
        <div
          className="rounded-xl border border-slate-200 bg-slate-50 p-4"
          key={bucket.key}
        >
          <div className="flex items-center justify-between gap-3">
            <p className="font-medium text-slate-900">{bucket.label}</p>
            <p className="text-sm text-slate-500">{bucket.projectCount} projects</p>
          </div>
          <div className="mt-2 grid gap-1 text-sm text-slate-600">
            <p>Quote {formatCurrency(bucket.quotedAmount, currencyCode)}</p>
            <p>Actual {formatCurrency(bucket.actualAmount, currencyCode)}</p>
            <p>
              Variance{" "}
              <span className="font-medium text-slate-900">
                {formatCurrency(bucket.varianceAmount, currencyCode)}
              </span>
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

export function DisciplineRangeTable({
  disciplineRanges,
}: {
  disciplineRanges: Array<{
    disciplineId: string;
    disciplineName?: string | null;
    low: number;
    median: number;
    high: number;
    currencyCode: string;
    sampleSize: number;
    observedVarianceMedianPct?: number | null;
  }>;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
              Discipline
            </th>
            <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
              Low
            </th>
            <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
              Median
            </th>
            <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
              High
            </th>
            <th className="border-b border-slate-200 pb-2 pr-4 font-medium">
              Sample
            </th>
            <th className="border-b border-slate-200 pb-2 font-medium">
              Variance
            </th>
          </tr>
        </thead>
        <tbody>
          {disciplineRanges.map((item) => (
            <tr className="text-slate-700" key={item.disciplineId}>
              <td className="border-b border-slate-100 py-3 pr-4 font-medium text-slate-900">
                {item.disciplineName ?? item.disciplineId}
              </td>
              <td className="border-b border-slate-100 py-3 pr-4">
                {formatCurrency(item.low, item.currencyCode)}
              </td>
              <td className="border-b border-slate-100 py-3 pr-4">
                {formatCurrency(item.median, item.currencyCode)}
              </td>
              <td className="border-b border-slate-100 py-3 pr-4">
                {formatCurrency(item.high, item.currencyCode)}
              </td>
              <td className="border-b border-slate-100 py-3 pr-4">
                {item.sampleSize}
              </td>
              <td className="border-b border-slate-100 py-3">
                {item.observedVarianceMedianPct == null
                  ? "—"
                  : formatPercent(item.observedVarianceMedianPct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
