import type {
  ForecastDisciplineMonthlyRollup,
  ForecastLineInput,
  ForecastLineResult,
  ForecastOutcomeBucket,
  ForecastOutcomeEvent,
  ForecastProjectMonthlyRollup,
  ForecastScheduleRange,
  ForecastScheduleResolutionResult,
  ForecastScheduleSlice,
  ForecastVersionCalculationInput,
  ForecastVersionCalculationResult,
  ManualAllocationInput,
  ManualAllocationValidationResult,
  ManualForecastOverrideInput,
  MonthlyAllocation,
  ProjectStatus,
  ScheduleAllocationInput,
  VarianceSummary,
  WeightedMonthlyAllocation
} from "./types.js";

function toUtcDate(value: Date | string): Date {
  const date = value instanceof Date ? value : new Date(`${value}T00:00:00Z`);

  if (Number.isNaN(date.getTime())) {
    throw new Error(`Invalid date value: ${String(value)}`);
  }

  return date;
}

function toMonthKey(date: Date): string {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(
    2,
    "0"
  )}`;
}

function firstDayOfNextMonth(date: Date): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 1));
}

function lastDayOfMonth(date: Date): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0));
}

function diffDaysInclusive(startDate: Date, endDate: Date): number {
  const millisecondsPerDay = 24 * 60 * 60 * 1000;
  return (
    Math.floor((endDate.getTime() - startDate.getTime()) / millisecondsPerDay) +
    1
  );
}

function toCents(amount: number): number {
  return Math.round(amount * 100);
}

function fromCents(amountInCents: number): number {
  return amountInCents / 100;
}

function toBasisPoints(percent: number): number {
  return Math.round(percent * 100);
}

function normalizePercent(percent: number): number {
  return Number(percent.toFixed(2));
}

function prefixIssues(prefix: string, issues: string[]): string[] {
  return issues.map((issue) => `${prefix}: ${issue}`);
}

function withOptionalProperty<Key extends string, Value>(
  key: Key,
  value: Value | undefined
): Partial<Record<Key, Value>> {
  if (value === undefined) {
    return {};
  }

  return { [key]: value } as Partial<Record<Key, Value>>;
}

function sortByFractionalRemainder<T extends { sortKey: string; raw: number; floor: number }>(
  items: T[]
): T[] {
  return items.slice().sort((left, right) => {
    const leftFraction = left.raw - left.floor;
    const rightFraction = right.raw - right.floor;

    if (rightFraction !== leftFraction) {
      return rightFraction - leftFraction;
    }

    return left.sortKey.localeCompare(right.sortKey);
  });
}

function buildWeightedMonthlyAllocations(
  allocations: MonthlyAllocation[],
  probabilityPercent: number
): WeightedMonthlyAllocation[] {
  const percentFactor = probabilityPercent / 100;
  const totalWeightedInCents = Math.round(
    allocations.reduce((sum, allocation) => sum + allocation.amountInCents, 0) * percentFactor
  );
  const weighted = allocations.map((allocation) => {
    const raw = allocation.amountInCents * percentFactor;
    const floor = Math.floor(raw);

    return {
      allocation,
      raw,
      floor,
      sortKey: allocation.month
    };
  });

  let remainder =
    totalWeightedInCents - weighted.reduce((sum, allocation) => sum + allocation.floor, 0);

  sortByFractionalRemainder(weighted).forEach((allocation) => {
    if (remainder <= 0) {
      return;
    }

    allocation.floor += 1;
    remainder -= 1;
  });

  return weighted
    .map((allocation) => ({
      ...allocation.allocation,
      weightedAmountInCents: allocation.floor,
      weightedAmount: fromCents(allocation.floor)
    }))
    .sort((left, right) => left.month.localeCompare(right.month));
}

function splitAmountAcrossSlices(
  totalAmount: number,
  slices: ForecastScheduleSlice[]
): Array<ForecastScheduleSlice & { allocatedAmountInCents: number; allocatedAmount: number }> {
  const totalAmountInCents = toCents(totalAmount);
  const allocations = slices.map((slice) => {
    const raw = (totalAmountInCents * toBasisPoints(slice.allocationPercent)) / 10000;
    const floor = Math.floor(raw);

    return {
      ...slice,
      raw,
      floor,
      sortKey: slice.scheduleRangeId
    };
  });

  let remainder =
    totalAmountInCents - allocations.reduce((sum, allocation) => sum + allocation.floor, 0);

  sortByFractionalRemainder(allocations).forEach((allocation) => {
    if (remainder <= 0) {
      return;
    }

    allocation.floor += 1;
    remainder -= 1;
  });

  return allocations.map((allocation) => ({
    scheduleRangeId: allocation.scheduleRangeId,
    scheduleRangeLabel: allocation.scheduleRangeLabel,
    startDate: allocation.startDate,
    endDate: allocation.endDate,
    allocationPercent: allocation.allocationPercent,
    allocatedAmountInCents: allocation.floor,
    allocatedAmount: fromCents(allocation.floor)
  }));
}

function validateScheduleRange(range: ForecastScheduleRange): string[] {
  const startDate = toUtcDate(range.startDate);
  const endDate = toUtcDate(range.endDate);

  if (endDate < startDate) {
    return [`Schedule range "${range.label}" ends before it starts.`];
  }

  return [];
}

function hasOverlaps(ranges: ForecastScheduleRange[]): boolean {
  const ordered = ranges
    .map((range) => ({
      ...range,
      startDateValue: toUtcDate(range.startDate).getTime(),
      endDateValue: toUtcDate(range.endDate).getTime()
    }))
    .sort((left, right) => left.startDateValue - right.startDateValue);

  for (let index = 1; index < ordered.length; index += 1) {
    const current = ordered[index];
    const previous = ordered[index - 1];

    if (current !== undefined && previous !== undefined && current.startDateValue <= previous.endDateValue) {
      return true;
    }
  }

  return false;
}

export function buildScheduleMonthlyAllocations(
  input: ScheduleAllocationInput
): MonthlyAllocation[] {
  const startDate = toUtcDate(input.startDate);
  const endDate = toUtcDate(input.endDate);

  if (endDate < startDate) {
    throw new Error("Schedule end date cannot be earlier than start date.");
  }

  if (input.amount < 0) {
    throw new Error("Schedule allocation amount cannot be negative.");
  }

  const totalDays = diffDaysInclusive(startDate, endDate);
  const totalAmountInCents = toCents(input.amount);
  const allocations: Array<{
    month: string;
    rawAmountInCents: number;
    flooredAmountInCents: number;
    sortKey: string;
  }> = [];

  let currentSliceStart = startDate;

  while (currentSliceStart <= endDate) {
    const currentSliceEnd = new Date(
      Math.min(lastDayOfMonth(currentSliceStart).getTime(), endDate.getTime())
    );
    const daysInSlice = diffDaysInclusive(currentSliceStart, currentSliceEnd);
    const rawAmountInCents = (totalAmountInCents * daysInSlice) / totalDays;

    allocations.push({
      month: toMonthKey(currentSliceStart),
      rawAmountInCents,
      flooredAmountInCents: Math.floor(rawAmountInCents),
      sortKey: toMonthKey(currentSliceStart)
    });

    currentSliceStart = firstDayOfNextMonth(currentSliceStart);
  }

  let remainder =
    totalAmountInCents -
    allocations.reduce((sum, item) => sum + item.flooredAmountInCents, 0);

  sortByFractionalRemainder(
    allocations.map((allocation) => ({
      sortKey: allocation.sortKey,
      raw: allocation.rawAmountInCents,
      floor: allocation.flooredAmountInCents
    }))
  ).forEach((allocation) => {
    if (remainder <= 0) {
      return;
    }

    const matchingAllocation = allocations.find((item) => item.sortKey === allocation.sortKey);

    if (matchingAllocation === undefined) {
      return;
    }

    matchingAllocation.flooredAmountInCents += 1;
    remainder -= 1;
  });

  return allocations
    .map((item) => ({
      month: item.month,
      amountInCents: item.flooredAmountInCents,
      amount: fromCents(item.flooredAmountInCents)
    }))
    .sort((left, right) => left.month.localeCompare(right.month));
}

export function validateManualMonthlyAllocations(
  input: ManualAllocationInput
): ManualAllocationValidationResult {
  const monthPattern = /^\d{4}-(0[1-9]|1[0-2])$/;
  const issues: string[] = [];
  const seenMonths = new Set<string>();

  const normalizedAllocations = input.allocations
    .map((allocation) => {
      if (!monthPattern.test(allocation.month)) {
        issues.push(`Invalid month format: ${allocation.month}`);
      }

      if (allocation.amount < 0) {
        issues.push(`Negative manual allocation is not allowed: ${allocation.month}`);
      }

      if (seenMonths.has(allocation.month)) {
        issues.push(`Duplicate manual allocation month: ${allocation.month}`);
      }

      seenMonths.add(allocation.month);

      return {
        month: allocation.month,
        amountInCents: toCents(allocation.amount),
        amount: Number(allocation.amount.toFixed(2))
      };
    })
    .sort((left, right) => left.month.localeCompare(right.month));

  const totalAmountInCents = normalizedAllocations.reduce((sum, allocation) => {
    return sum + allocation.amountInCents;
  }, 0);
  const expectedAmountInCents = toCents(input.expectedAmount);
  const differenceInCents = totalAmountInCents - expectedAmountInCents;

  if (differenceInCents !== 0) {
    issues.push(
      `Manual allocations total ${fromCents(totalAmountInCents).toFixed(
        2
      )} but expected ${input.expectedAmount.toFixed(2)}`
    );
  }

  return {
    isValid: issues.length === 0,
    normalizedAllocations,
    totalAmount: fromCents(totalAmountInCents),
    differenceFromExpected: fromCents(differenceInCents),
    issues
  };
}

export function resolveForecastOutcomeBucket(input: {
  projectStatus: ProjectStatus;
  outcomes: ForecastOutcomeEvent[];
}): ForecastOutcomeBucket {
  if (input.projectStatus === "lost") {
    return "lost";
  }

  const latestTerminalOutcome = input.outcomes
    .filter((outcome) => outcome.outcomeType !== "bid")
    .sort((left, right) => {
      return toUtcDate(right.effectiveAt).getTime() - toUtcDate(left.effectiveAt).getTime();
    })[0];

  if (latestTerminalOutcome !== undefined) {
    return latestTerminalOutcome.outcomeType;
  }

  if (
    input.projectStatus === "awarded" ||
    input.projectStatus === "active" ||
    input.projectStatus === "complete"
  ) {
    return "awarded";
  }

  return "bid";
}

export function normalizeForecastProbability(input: {
  bucket: ForecastOutcomeBucket;
  requestedProbabilityPercent?: number;
}): number {
  const requested = input.requestedProbabilityPercent;

  if (requested !== undefined && (!Number.isFinite(requested) || requested < 0 || requested > 100)) {
    throw new Error("Forecast probability percent must be between 0 and 100.");
  }

  if (input.bucket === "awarded") {
    return 100;
  }

  if (input.bucket === "lost") {
    return 0;
  }

  return normalizePercent(requested ?? 100);
}

export function resolveForecastScheduleSlices(input: {
  line: Pick<ForecastLineInput, "disciplineId" | "label" | "scheduleRangeId">;
  scheduleRanges: ForecastScheduleRange[];
}): ForecastScheduleResolutionResult {
  if (input.line.scheduleRangeId !== undefined) {
    const exactRange = input.scheduleRanges.find((range) => range.id === input.line.scheduleRangeId);

    if (exactRange === undefined) {
      return {
        isValid: false,
        issues: [`Schedule range ${input.line.scheduleRangeId} was not found.`],
        slices: []
      };
    }

    return {
      isValid: validateScheduleRange(exactRange).length === 0,
      issues: validateScheduleRange(exactRange),
      slices: [
        {
          scheduleRangeId: exactRange.id,
          scheduleRangeLabel: exactRange.label,
          startDate: exactRange.startDate,
          endDate: exactRange.endDate,
          allocationPercent: 100
        }
      ]
    };
  }

  if (input.line.disciplineId === undefined) {
    return {
      isValid: false,
      issues: [`Schedule line "${input.line.label}" requires a discipline.`],
      slices: []
    };
  }

  const disciplineRanges = input.scheduleRanges.filter(
    (range) => range.disciplineId === input.line.disciplineId
  );
  const candidateRanges =
    disciplineRanges.length > 0
      ? disciplineRanges
      : input.scheduleRanges.filter((range) => range.disciplineId === undefined);

  if (candidateRanges.length === 0) {
    return {
      isValid: false,
      issues: [`No schedule ranges were found for "${input.line.label}".`],
      slices: []
    };
  }

  const rangeIssues = candidateRanges.flatMap(validateScheduleRange);

  if (rangeIssues.length > 0) {
    return {
      isValid: false,
      issues: rangeIssues,
      slices: []
    };
  }

  if (candidateRanges.length === 1) {
    const singleRange = candidateRanges[0];

    if (singleRange === undefined) {
      return {
        isValid: false,
        issues: [`No schedule ranges were found for "${input.line.label}".`],
        slices: []
      };
    }

    return {
      isValid: true,
      issues: [],
      slices: [
        {
          scheduleRangeId: singleRange.id,
          scheduleRangeLabel: singleRange.label,
          startDate: singleRange.startDate,
          endDate: singleRange.endDate,
          allocationPercent: 100
        }
      ]
    };
  }

  if (hasOverlaps(candidateRanges)) {
    return {
      isValid: false,
      issues: [`Schedule ranges overlap for "${input.line.label}".`],
      slices: []
    };
  }

  const missingPercentages = candidateRanges.filter(
    (range) => range.allocationPercent === undefined || range.allocationPercent <= 0
  );

  if (missingPercentages.length > 0) {
    return {
      isValid: false,
      issues: [`Schedule ranges for "${input.line.label}" need allocation percentages.`],
      slices: []
    };
  }

  const totalBasisPoints = candidateRanges.reduce((sum, range) => {
    return sum + toBasisPoints(range.allocationPercent ?? 0);
  }, 0);

  if (totalBasisPoints !== 10000) {
    return {
      isValid: false,
      issues: [`Schedule range percentages for "${input.line.label}" must total 100.`],
      slices: []
    };
  }

  return {
    isValid: true,
    issues: [],
    slices: candidateRanges
      .map((range) => ({
        scheduleRangeId: range.id,
        scheduleRangeLabel: range.label,
        startDate: range.startDate,
        endDate: range.endDate,
        allocationPercent: normalizePercent(range.allocationPercent ?? 0)
      }))
      .sort((left, right) => {
        return toUtcDate(left.startDate).getTime() - toUtcDate(right.startDate).getTime();
      })
  };
}

function buildScheduleLineResults(input: {
  line: ForecastLineInput;
  probabilityPercent: number;
  slices: ForecastScheduleSlice[];
}): ForecastLineResult[] {
  const splitAllocations = splitAmountAcrossSlices(input.line.totalAmount, input.slices);

  return splitAllocations.map((slice, index) => {
    const monthlyAllocations = buildScheduleMonthlyAllocations({
      startDate: slice.startDate,
      endDate: slice.endDate,
      amount: slice.allocatedAmount,
      currencyCode: input.line.currencyCode,
      ...withOptionalProperty("disciplineId", input.line.disciplineId)
    });
    const weightedAllocations = buildWeightedMonthlyAllocations(
      monthlyAllocations,
      input.probabilityPercent
    );
    const totalAmountInCents = monthlyAllocations.reduce((sum, allocation) => {
      return sum + allocation.amountInCents;
    }, 0);

    return {
      id:
        splitAllocations.length === 1
          ? input.line.id
          : `${input.line.id}:${index + 1}:${slice.scheduleRangeId}`,
      sourceLineId: input.line.id,
      label:
        splitAllocations.length === 1
          ? input.line.label
          : `${input.line.label} - ${slice.scheduleRangeLabel}`,
      totalAmount: fromCents(totalAmountInCents),
      totalAmountInCents,
      currencyCode: input.line.currencyCode,
      allocationMethod: "schedule",
      issues: [],
      allocations: weightedAllocations,
      ...withOptionalProperty("disciplineId", input.line.disciplineId),
      ...withOptionalProperty("scheduleRangeId", slice.scheduleRangeId),
      ...withOptionalProperty("notes", input.line.notes)
    };
  });
}

function buildManualLineResult(input: {
  line: ForecastLineInput;
  probabilityPercent: number;
}): ForecastLineResult {
  const validation = validateManualMonthlyAllocations({
    expectedAmount: input.line.totalAmount,
    allocations: input.line.allocations ?? []
  });
  const weightedAllocations = buildWeightedMonthlyAllocations(
    validation.normalizedAllocations,
    input.probabilityPercent
  );
  const totalAmountInCents = validation.normalizedAllocations.reduce((sum, allocation) => {
    return sum + allocation.amountInCents;
  }, 0);

  return {
    id: input.line.id,
    sourceLineId: input.line.id,
    label: input.line.label,
    totalAmount: fromCents(totalAmountInCents),
    totalAmountInCents,
    currencyCode: input.line.currencyCode,
    allocationMethod: "manual",
    issues: validation.issues,
    allocations: weightedAllocations,
    ...withOptionalProperty("disciplineId", input.line.disciplineId),
    ...withOptionalProperty("scheduleRangeId", input.line.scheduleRangeId),
    ...withOptionalProperty("notes", input.line.notes)
  };
}

function buildInvalidScheduleLineResult(line: ForecastLineInput, issues: string[]): ForecastLineResult {
  return {
    id: line.id,
    sourceLineId: line.id,
    label: line.label,
    totalAmount: 0,
    totalAmountInCents: 0,
    currencyCode: line.currencyCode,
    allocationMethod: "schedule",
    issues,
    allocations: [],
    ...withOptionalProperty("disciplineId", line.disciplineId),
    ...withOptionalProperty("scheduleRangeId", line.scheduleRangeId),
    ...withOptionalProperty("notes", line.notes)
  };
}

function buildDisciplineMonthlyRollups(lines: ForecastLineResult[]): ForecastDisciplineMonthlyRollup[] {
  const rollups = new Map<string, ForecastDisciplineMonthlyRollup>();

  lines.forEach((line) => {
    line.allocations.forEach((allocation) => {
      const disciplineKey = line.disciplineId ?? "unassigned";
      const key = `${disciplineKey}:${allocation.month}`;
      const current = rollups.get(key);

      if (current === undefined) {
        rollups.set(key, {
          month: allocation.month,
          amount: allocation.amount,
          amountInCents: allocation.amountInCents,
          weightedAmount: allocation.weightedAmount,
          weightedAmountInCents: allocation.weightedAmountInCents,
          ...withOptionalProperty("disciplineId", line.disciplineId)
        });
        return;
      }

      current.amountInCents += allocation.amountInCents;
      current.weightedAmountInCents += allocation.weightedAmountInCents;
      current.amount = fromCents(current.amountInCents);
      current.weightedAmount = fromCents(current.weightedAmountInCents);
    });
  });

  return Array.from(rollups.values()).sort((left, right) => {
    if (left.disciplineId !== right.disciplineId) {
      return (left.disciplineId ?? "").localeCompare(right.disciplineId ?? "");
    }

    return left.month.localeCompare(right.month);
  });
}

function buildProjectMonthlyRollups(
  disciplineRollups: ForecastDisciplineMonthlyRollup[]
): ForecastProjectMonthlyRollup[] {
  const rollups = new Map<string, ForecastProjectMonthlyRollup>();

  disciplineRollups.forEach((rollup) => {
    const current = rollups.get(rollup.month);

    if (current === undefined) {
      rollups.set(rollup.month, {
        month: rollup.month,
        amount: rollup.amount,
        amountInCents: rollup.amountInCents,
        weightedAmount: rollup.weightedAmount,
        weightedAmountInCents: rollup.weightedAmountInCents
      });
      return;
    }

    current.amountInCents += rollup.amountInCents;
    current.weightedAmountInCents += rollup.weightedAmountInCents;
    current.amount = fromCents(current.amountInCents);
    current.weightedAmount = fromCents(current.weightedAmountInCents);
  });

  return Array.from(rollups.values()).sort((left, right) => left.month.localeCompare(right.month));
}

export function calculateForecastVersion(
  input: ForecastVersionCalculationInput
): ForecastVersionCalculationResult {
  const outcomeTypeSnapshot = resolveForecastOutcomeBucket({
    projectStatus: input.projectStatus,
    outcomes: input.outcomes
  });
  const probabilityPercent =
    input.probabilityPercent === undefined
      ? normalizeForecastProbability({ bucket: outcomeTypeSnapshot })
      : normalizeForecastProbability({
          bucket: outcomeTypeSnapshot,
          requestedProbabilityPercent: input.probabilityPercent
        });
  const lines: ForecastLineResult[] = [];
  const issues: string[] = [];

  input.lines.forEach((line) => {
    if (line.totalAmount < 0) {
      const lineIssues = [`${line.label}: Forecast line total cannot be negative.`];
      issues.push(...lineIssues);
      lines.push(buildInvalidScheduleLineResult(line, lineIssues));
      return;
    }

    if (line.allocationMethod === "manual") {
      const manualLine = buildManualLineResult({ line, probabilityPercent });
      issues.push(...prefixIssues(line.label, manualLine.issues));
      lines.push(manualLine);
      return;
    }

    const scheduleResolution = resolveForecastScheduleSlices({
      line,
      scheduleRanges: input.scheduleRanges
    });

    if (!scheduleResolution.isValid) {
      const lineIssues = prefixIssues(line.label, scheduleResolution.issues);
      issues.push(...lineIssues);
      lines.push(buildInvalidScheduleLineResult(line, lineIssues));
      return;
    }

    lines.push(
      ...buildScheduleLineResults({
        line,
        probabilityPercent,
        slices: scheduleResolution.slices
      })
    );
  });

  const totalAmountInCents = lines.reduce((sum, line) => sum + line.totalAmountInCents, 0);
  const weightedTotalAmountInCents = lines.reduce((sum, line) => {
    return (
      sum +
      line.allocations.reduce((allocationSum, allocation) => {
        return allocationSum + allocation.weightedAmountInCents;
      }, 0)
    );
  }, 0);
  const disciplineMonthlyRollups = buildDisciplineMonthlyRollups(lines);
  const projectMonthlyRollups = buildProjectMonthlyRollups(disciplineMonthlyRollups);

  return {
    outcomeTypeSnapshot,
    probabilityPercent,
    totalAmount: fromCents(totalAmountInCents),
    totalAmountInCents,
    weightedTotalAmount: fromCents(weightedTotalAmountInCents),
    weightedTotalAmountInCents,
    lines,
    disciplineMonthlyRollups,
    projectMonthlyRollups,
    issues
  };
}

export function applyManualForecastOverride(
  input: ManualForecastOverrideInput
): ForecastLineInput {
  const reasonSuffix = input.reason ? `Manual override: ${input.reason}` : "Manual override";

  return {
    id: input.line.id,
    label: input.line.label,
    totalAmount: input.line.totalAmount,
    currencyCode: input.line.currencyCode,
    allocationMethod: "manual",
    allocations: input.allocations,
    notes: input.line.notes ? `${input.line.notes}\n${reasonSuffix}` : reasonSuffix,
    ...withOptionalProperty("disciplineId", input.line.disciplineId)
  };
}

export function summarizeVariance(input: {
  quotedAmount: number;
  forecastAmount: number;
  actualAmount: number;
}): VarianceSummary {
  return {
    quotedAmount: Number(input.quotedAmount.toFixed(2)),
    forecastAmount: Number(input.forecastAmount.toFixed(2)),
    actualAmount: Number(input.actualAmount.toFixed(2)),
    quoteToActualVariance: Number((input.actualAmount - input.quotedAmount).toFixed(2)),
    forecastToActualVariance: Number(
      (input.actualAmount - input.forecastAmount).toFixed(2)
    )
  };
}
