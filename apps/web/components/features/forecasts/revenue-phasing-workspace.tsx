"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  default as React,
  Fragment,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
  useTransition,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import type {
  ForecastPhasingCellRead,
  ForecastPhasingDraftRead,
  ForecastPhasingDraftStateRead,
  ForecastPhasingWorkspaceRead,
} from "@quotes4/contracts";
import { ApiClientError } from "@quotes4/contracts";

import { getBrowserApiClient } from "@/lib/api/browser-client";
import { cn } from "@/lib/classnames";
import { formatCurrency, formatDateTime, formatStatusLabel } from "@/lib/format";
import { queryKeys } from "@/lib/query/keys";

import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SelectField } from "@/components/forms/select-field";
import { TextAreaField } from "@/components/forms/text-area-field";

type RowMode = "project" | "discipline";

type PhasingFilters = {
  fromMonth: string;
  toMonth: string;
  clientId: string | undefined;
  projectId: string | undefined;
  disciplineId: string | undefined;
  status: string | undefined;
  scenarioKey: string | undefined;
  rowMode: RowMode;
};

type DraftCell = {
  amount: string;
  isLocked: boolean;
};

type SaveMode = "replace" | "merge";

type RowDraft = {
  expectedUpdatedAt: string;
  forecastVersionId: string | null | undefined;
  reason: string;
  cells: Record<string, DraftCell>;
};

type DraftHistoryState = {
  past: RowDraft[];
  future: RowDraft[];
};

type DraftConflictState = {
  baselineDraft: RowDraft;
  baselineSaveMode: SaveMode;
  message: string;
};

type DraftSyncState = {
  draft: RowDraft;
  draftUpdatedAt: string | null;
  history: DraftHistoryState;
  saveMode: SaveMode;
};

type EditorState = {
  drafts: Record<string, RowDraft>;
  histories: Record<string, DraftHistoryState>;
  saveModes: Record<string, SaveMode>;
  draftUpdatedAts: Record<string, string | null>;
};

type CellSelection = {
  anchorRowKey: string;
  anchorMonth: string;
  focusRowKey: string;
  focusMonth: string;
};

type FillDragState = {
  sourceSelection: CellSelection;
  sourceCells: Array<{
    rowOffset: number;
    monthOffset: number;
    value: DraftCell;
  }>;
};

const STATUS_CHART_KEYS = ["bid", "awarded", "lost"] as const;
const STATUS_CHART_COLORS: Record<(typeof STATUS_CHART_KEYS)[number], string> = {
  bid: "#0ea5e9",
  awarded: "#0f172a",
  lost: "#f97316",
};

function isMonthValue(value: string | null | undefined): value is string {
  return typeof value === "string" && /^\d{4}-\d{2}$/.test(value);
}

function shiftMonth(referenceDate: Date, delta: number): string {
  const value = new Date(
    Date.UTC(referenceDate.getUTCFullYear(), referenceDate.getUTCMonth(), 1),
  );
  value.setUTCMonth(value.getUTCMonth() + delta);
  return `${value.getUTCFullYear()}-${String(value.getUTCMonth() + 1).padStart(2, "0")}`;
}

function getDefaultFilters(referenceDate = new Date()): PhasingFilters {
  return {
    clientId: undefined,
    disciplineId: undefined,
    fromMonth: shiftMonth(referenceDate, 0),
    projectId: undefined,
    toMonth: shiftMonth(referenceDate, 17),
    rowMode: "project",
    scenarioKey: "base",
    status: undefined,
  };
}

function toDraftCell(amount: string, isLocked: boolean | null | undefined): DraftCell {
  return {
    amount,
    isLocked: Boolean(isLocked),
  };
}

function cloneRowDraft(draft: RowDraft): RowDraft {
  return {
    expectedUpdatedAt: draft.expectedUpdatedAt,
    forecastVersionId: draft.forecastVersionId,
    reason: draft.reason,
    cells: Object.fromEntries(
      Object.entries(draft.cells).map(([month, value]) => [
        month,
        toDraftCell(value.amount, value.isLocked),
      ]),
    ),
  };
}

function buildDraftFromState(state: ForecastPhasingDraftStateRead): RowDraft {
  return {
    expectedUpdatedAt: state.expectedUpdatedAt,
    forecastVersionId: state.forecastVersionId,
    reason: state.reason ?? "",
    cells: Object.fromEntries(
      (state.cells ?? []).map((cell: NonNullable<ForecastPhasingDraftStateRead["cells"]>[number]) => [
        cell.month,
        toDraftCell(String(cell.amount), cell.isLocked),
      ]),
    ),
  };
}

function getEmptyDraftHistory(): DraftHistoryState {
  return {
    past: [],
    future: [],
  };
}

function draftsEqual(left: RowDraft, right: RowDraft): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function draftCellsEqual(
  left: DraftCell | null | undefined,
  right: DraftCell | null | undefined,
): boolean {
  if (!left && !right) {
    return true;
  }
  if (!left || !right) {
    return false;
  }
  return left.amount === right.amount && left.isLocked === right.isLocked;
}

function isEffectiveDraftCell(cell: DraftCell): boolean {
  const amount = Number(cell.amount);
  return cell.isLocked || (Number.isFinite(amount) && Math.abs(amount) > 0.009);
}

function countEffectiveDraftCells(draft: RowDraft | undefined): number {
  if (!draft) {
    return 0;
  }
  return Object.values(draft.cells).filter((cell) => isEffectiveDraftCell(cell)).length;
}

function getChangedDraftMonths(baselineDraft: RowDraft, currentDraft: RowDraft): string[] {
  const months = new Set([
    ...Object.keys(baselineDraft.cells),
    ...Object.keys(currentDraft.cells),
  ]);
  return Array.from(months)
    .filter((month) => !draftCellsEqual(baselineDraft.cells[month], currentDraft.cells[month]))
    .sort((left, right) => left.localeCompare(right));
}

function mergeDraftOntoLatest(
  latestDraft: RowDraft,
  baselineDraft: RowDraft,
  localDraft: RowDraft,
): RowDraft {
  const mergedDraft = cloneRowDraft(latestDraft);
  const changedMonths = getChangedDraftMonths(baselineDraft, localDraft);

  changedMonths.forEach((month) => {
    const localCell = localDraft.cells[month];
    if (localCell && isEffectiveDraftCell(localCell)) {
      mergedDraft.cells[month] = toDraftCell(localCell.amount, localCell.isLocked);
      return;
    }
    delete mergedDraft.cells[month];
  });

  if (localDraft.reason !== baselineDraft.reason) {
    mergedDraft.reason = localDraft.reason;
  }
  if (localDraft.forecastVersionId !== baselineDraft.forecastVersionId) {
    mergedDraft.forecastVersionId = localDraft.forecastVersionId;
  }
  mergedDraft.expectedUpdatedAt = latestDraft.expectedUpdatedAt;
  return mergedDraft;
}

function buildSelectedMonths(
  selection: CellSelection | null,
  rowKeys: string[],
  months: string[],
): string[] {
  if (!selection) {
    return [];
  }
  const anchorRowIndex = rowKeys.indexOf(selection.anchorRowKey);
  const focusRowIndex = rowKeys.indexOf(selection.focusRowKey);
  const anchorIndex = months.indexOf(selection.anchorMonth);
  const focusIndex = months.indexOf(selection.focusMonth);
  if (anchorRowIndex < 0 || focusRowIndex < 0 || anchorIndex < 0 || focusIndex < 0) {
    return [];
  }
  const startIndex = Math.min(anchorIndex, focusIndex);
  const endIndex = Math.max(anchorIndex, focusIndex);
  return months.slice(startIndex, endIndex + 1);
}

function buildSelectedGrid(
  selection: CellSelection | null,
  rowKeys: string[],
  months: string[],
) {
  if (!selection) {
    return {
      cells: [] as Array<{ month: string; monthOffset: number; rowKey: string; rowOffset: number }>,
      months: [] as string[],
      rowKeys: [] as string[],
    };
  }
  const anchorRowIndex = rowKeys.indexOf(selection.anchorRowKey);
  const focusRowIndex = rowKeys.indexOf(selection.focusRowKey);
  const anchorMonthIndex = months.indexOf(selection.anchorMonth);
  const focusMonthIndex = months.indexOf(selection.focusMonth);
  if (
    anchorRowIndex < 0 ||
    focusRowIndex < 0 ||
    anchorMonthIndex < 0 ||
    focusMonthIndex < 0
  ) {
    return {
      cells: [] as Array<{ month: string; monthOffset: number; rowKey: string; rowOffset: number }>,
      months: [] as string[],
      rowKeys: [] as string[],
    };
  }
  const selectedRowKeys = rowKeys.slice(
    Math.min(anchorRowIndex, focusRowIndex),
    Math.max(anchorRowIndex, focusRowIndex) + 1,
  );
  const selectedMonths = months.slice(
    Math.min(anchorMonthIndex, focusMonthIndex),
    Math.max(anchorMonthIndex, focusMonthIndex) + 1,
  );
  return {
    rowKeys: selectedRowKeys,
    months: selectedMonths,
    cells: selectedRowKeys.flatMap((rowKey, rowOffset) =>
      selectedMonths.map((month, monthOffset) => ({
        rowKey,
        month,
        rowOffset,
        monthOffset,
      })),
    ),
  };
}

function describeMonthRange(months: string[]): string {
  if (months.length === 0) {
    return "No months selected";
  }
  const firstMonth = months[0];
  const lastMonth = months[months.length - 1];
  if (!firstMonth || !lastMonth) {
    return "No months selected";
  }
  if (months.length === 1) {
    return formatMonthLabel(firstMonth);
  }
  return `${formatMonthLabel(firstMonth)} to ${formatMonthLabel(lastMonth)}`;
}

function describeSelectionRange(rowCount: number, months: string[]): string {
  if (rowCount === 0 || months.length === 0) {
    return "No cells selected";
  }
  return `${rowCount} row${rowCount === 1 ? "" : "s"} × ${months.length} month${months.length === 1 ? "" : "s"} · ${describeMonthRange(months)}`;
}

function toWorkspaceQueryOptions(filters: PhasingFilters) {
  return {
    ...(filters.clientId ? { clientId: filters.clientId } : {}),
    ...(filters.disciplineId ? { disciplineId: filters.disciplineId } : {}),
    ...(filters.fromMonth ? { fromMonth: filters.fromMonth } : {}),
    ...(filters.projectId ? { projectId: filters.projectId } : {}),
    ...(filters.rowMode ? { rowMode: filters.rowMode } : {}),
    ...(filters.scenarioKey ? { scenarioKey: filters.scenarioKey } : {}),
    ...(filters.status ? { status: filters.status } : {}),
    ...(filters.toMonth ? { toMonth: filters.toMonth } : {}),
  };
}

function parseFilters(
  source: string | URLSearchParams | { toString(): string },
  fallback: ForecastPhasingWorkspaceRead,
): PhasingFilters {
  const params =
    typeof source === "string"
      ? new URLSearchParams(source)
      : source instanceof URLSearchParams
        ? new URLSearchParams(source)
        : new URLSearchParams(source.toString());
  const defaults = getDefaultFilters();
  return {
    fromMonth: isMonthValue(params.get("fromMonth"))
      ? (params.get("fromMonth") as string)
      : fallback.fromMonth ?? defaults.fromMonth,
    toMonth: isMonthValue(params.get("toMonth"))
      ? (params.get("toMonth") as string)
      : fallback.toMonth ?? defaults.toMonth,
    clientId: params.get("clientId") || undefined,
    projectId: params.get("projectId") || undefined,
    disciplineId: params.get("disciplineId") || undefined,
    status: params.get("status") || undefined,
    scenarioKey: params.get("scenarioKey") || fallback.scenarioKey || "base",
    rowMode:
      params.get("rowMode") === "discipline"
        ? "discipline"
        : (fallback.rowMode as RowMode) || defaults.rowMode,
  };
}

function serializeFilters(filters: PhasingFilters): string {
  const params = new URLSearchParams();
  params.set("fromMonth", filters.fromMonth);
  params.set("toMonth", filters.toMonth);
  params.set("rowMode", filters.rowMode);
  if (filters.clientId) params.set("clientId", filters.clientId);
  if (filters.projectId) params.set("projectId", filters.projectId);
  if (filters.disciplineId) params.set("disciplineId", filters.disciplineId);
  if (filters.status) params.set("status", filters.status);
  if (filters.scenarioKey) params.set("scenarioKey", filters.scenarioKey);
  return params.toString();
}

function formatMonthLabel(month: string): string {
  if (!isMonthValue(month)) {
    return month;
  }
  const [year, monthValue] = month.split("-");
  return new Intl.DateTimeFormat("en-GB", {
    month: "short",
    year: "2-digit",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(Number(year), Number(monthValue) - 1, 1)));
}

function buildDraft(row: ForecastPhasingWorkspaceRead["rows"][number]): RowDraft {
  if (row.activeDraft) {
    return buildDraftFromState(row.activeDraft.currentState);
  }
  return {
    expectedUpdatedAt: row.forecastVersionUpdatedAt ?? "",
    forecastVersionId: row.forecastVersionId,
    reason: "",
    cells: Object.fromEntries(
      (row.cells ?? [])
        .filter((cell) => cell.isManualOverride || cell.isLocked)
        .map((cell) => [cell.month, toDraftCell(String(cell.amount), cell.isLocked)]),
    ),
  };
}

function buildDraftHistory(
  row: ForecastPhasingWorkspaceRead["rows"][number],
): DraftHistoryState {
  if (!row.activeDraft) {
    return getEmptyDraftHistory();
  }
  return {
    past: (row.activeDraft.pastStates ?? []).map((state) => buildDraftFromState(state)),
    future: (row.activeDraft.futureStates ?? []).map((state) => buildDraftFromState(state)),
  };
}

function buildDraftSaveMode(row: ForecastPhasingWorkspaceRead["rows"][number]): SaveMode {
  return row.activeDraft?.saveMode === "merge" ? "merge" : "replace";
}

function buildDraftUpdatedAt(row: ForecastPhasingWorkspaceRead["rows"][number]): string | null {
  return row.activeDraft?.updatedAt ?? null;
}

function buildDraftStatePayload(draft: RowDraft): ForecastPhasingDraftStateRead {
  return {
    forecastVersionId: draft.forecastVersionId ?? null,
    expectedUpdatedAt: draft.expectedUpdatedAt,
    reason: draft.reason || null,
    cells: Object.entries(draft.cells)
      .filter(([, value]) => isEffectiveDraftCell(value))
      .map(([month, value]) => ({
        month,
        amount: Number(value.amount),
        isLocked: value.isLocked,
        note: null,
      }))
      .sort((left, right) => left.month.localeCompare(right.month)),
  };
}

function getDisplayCellValue(
  cell: ForecastPhasingCellRead,
  draft: RowDraft | undefined,
): string {
  return draft?.cells[cell.month]?.amount ?? String(cell.amount);
}

function getCellLockValue(
  cell: ForecastPhasingCellRead,
  draft: RowDraft | undefined,
): boolean {
  return Boolean(draft?.cells[cell.month]?.isLocked ?? cell.isLocked);
}

function sumManualDraftValues(draft: RowDraft | undefined): number {
  if (!draft) {
    return 0;
  }
  return Number(
    Object.values(draft.cells)
      .reduce((sum, cell) => {
        const amount = Number(cell.amount);
        return Number.isFinite(amount) ? sum + amount : sum;
      }, 0)
      .toFixed(2),
  );
}

function buildStatusSeries(workspace: ForecastPhasingWorkspaceRead) {
  return STATUS_CHART_KEYS.map((statusKey) => ({
    statusKey,
    label: formatStatusLabel(statusKey),
    points: workspace.months.map((month) => {
      const matching = (workspace.statusMonthTotals ?? []).find(
        (item) => item.status === statusKey && item.month === month,
      );
      return matching?.amount ?? 0;
    }),
  }));
}

function StatusTrendChart({ workspace }: { workspace: ForecastPhasingWorkspaceRead }) {
  const width = 780;
  const height = 220;
  const paddingX = 40;
  const paddingY = 20;
  const series = buildStatusSeries(workspace);
  const maxValue = Math.max(
    1,
    ...series.flatMap((item) => item.points),
  );
  const pointX = (index: number) =>
    workspace.months.length === 1
      ? width / 2
      : paddingX + ((width - paddingX * 2) / (workspace.months.length - 1)) * index;
  const pointY = (value: number) =>
    height - paddingY - (value / maxValue) * (height - paddingY * 2);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 text-xs text-slate-500">
        {series.map((item) => (
          <div className="flex items-center gap-2" key={item.statusKey}>
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: STATUS_CHART_COLORS[item.statusKey] }}
            />
            {item.label}
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
        <svg
          aria-label="Revenue phasing status trend"
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
                <text fill="#64748b" fontSize="11" x={0} y={y + 4}>
                  {formatCurrency(labelValue, "GBP")}
                </text>
              </g>
            );
          })}
          {series.map((item) => {
            const points = item.points
              .map((value, index) => `${pointX(index)},${pointY(value)}`)
              .join(" ");
            return (
              <polyline
                fill="none"
                key={item.statusKey}
                points={points}
                stroke={STATUS_CHART_COLORS[item.statusKey]}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="3"
              />
            );
          })}
        </svg>
      </div>
    </div>
  );
}

export function RevenuePhasingWorkspace({
  initialWorkspace,
}: {
  initialWorkspace: ForecastPhasingWorkspaceRead;
}) {
  const api = getBrowserApiClient();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [isPending, startTransition] = useTransition();
  const [selectedRowKey, setSelectedRowKey] = useState<string | null>(
    initialWorkspace.rows[0]?.rowKey ?? null,
  );
  const [editorState, setEditorState] = useState<EditorState>({
    drafts: {},
    histories: {},
    saveModes: {},
    draftUpdatedAts: {},
  });
  const [collapsedProjects, setCollapsedProjects] = useState<Record<string, boolean>>({});
  const [previewProfileType, setPreviewProfileType] = useState("flat_equal");
  const [cellSelection, setCellSelection] = useState<CellSelection | null>(null);
  const [fillDragState, setFillDragState] = useState<FillDragState | null>(null);
  const [draftSyncErrors, setDraftSyncErrors] = useState<Record<string, string | null>>({});
  const [draftConflicts, setDraftConflicts] = useState<Record<string, DraftConflictState | null>>(
    {},
  );
  const [resolvingConflictRowKeys, setResolvingConflictRowKeys] = useState<
    Record<string, boolean>
  >({});
  const [syncingRowKeys, setSyncingRowKeys] = useState<Record<string, boolean>>({});
  const draftSyncTimersRef = useRef<Record<string, number>>({});
  const pendingCellFocusRef = useRef<{
    extendSelection: boolean;
    month: string;
    rowKey: string;
  } | null>(null);
  const editorStateRef = useRef(editorState);
  const rowsByKeyRef = useRef<Record<string, ForecastPhasingWorkspaceRead["rows"][number]>>({});
  const search = searchParams.toString();
  const deferredSearch = useDeferredValue(search);
  const filters = parseFilters(search, initialWorkspace);
  const queryFilters = parseFilters(deferredSearch, initialWorkspace);
  const filtersKey = serializeFilters(queryFilters);

  const workspaceQuery = useQuery({
    initialData: initialWorkspace,
    placeholderData: (previous) => previous,
    queryFn: async () => api.getForecastPhasingWorkspace(toWorkspaceQueryOptions(queryFilters)),
    queryKey: queryKeys.forecastPhasingWorkspace(filtersKey),
    refetchInterval: 15000,
  });

  const workspace = workspaceQuery.data ?? initialWorkspace;

  useEffect(() => {
    editorStateRef.current = editorState;
  }, [editorState]);

  useEffect(() => {
    if (!selectedRowKey || workspace.rows.some((row) => row.rowKey === selectedRowKey)) {
      return;
    }
    setSelectedRowKey(workspace.rows[0]?.rowKey ?? null);
  }, [selectedRowKey, workspace.rows]);

  const rowsByKey = useMemo(
    () => Object.fromEntries(workspace.rows.map((row) => [row.rowKey, row])),
    [workspace.rows],
  );

  useEffect(() => {
    rowsByKeyRef.current = rowsByKey;
  }, [rowsByKey]);

  const groupedRows = useMemo(() => {
    if (filters.rowMode !== "discipline") {
      return [];
    }
    const groups = new Map<string, ForecastPhasingWorkspaceRead["rows"]>();
    workspace.rows.forEach((row) => {
      const current = groups.get(row.projectId) ?? [];
      current.push(row);
      groups.set(row.projectId, current);
    });
    return Array.from(groups.entries()).map(([projectId, rows]) => ({
      projectId,
      projectName: rows[0]?.projectName ?? projectId,
      rows,
    }));
  }, [filters.rowMode, workspace.rows]);
  const visibleRows = useMemo(
    () =>
      filters.rowMode === "discipline"
        ? groupedRows.flatMap((group) =>
            collapsedProjects[group.projectId] ? [] : group.rows,
          )
        : workspace.rows,
    [collapsedProjects, filters.rowMode, groupedRows, workspace.rows],
  );
  const visibleRowKeys = useMemo(
    () => visibleRows.map((row) => row.rowKey),
    [visibleRows],
  );
  const selectedRow = selectedRowKey ? rowsByKey[selectedRowKey] ?? null : null;
  const selectedDraft = selectedRow
    ? editorState.drafts[selectedRow.rowKey] ?? buildDraft(selectedRow)
    : undefined;
  const selectedHistory = selectedRow
    ? editorState.histories[selectedRow.rowKey] ?? buildDraftHistory(selectedRow)
    : getEmptyDraftHistory();
  const selectedSaveMode = selectedRow
    ? editorState.saveModes[selectedRow.rowKey] ?? buildDraftSaveMode(selectedRow)
    : "replace";
  const selectedConflict = selectedRow ? draftConflicts[selectedRow.rowKey] ?? null : null;
  const selectedConflictMonths = selectedConflict && selectedDraft
    ? getChangedDraftMonths(selectedConflict.baselineDraft, selectedDraft)
    : [];
  const selectedGrid = useMemo(
    () => buildSelectedGrid(cellSelection, visibleRowKeys, workspace.months),
    [cellSelection, visibleRowKeys, workspace.months],
  );
  const selectedMonths = selectedGrid.months;
  const selectedRowKeys = selectedGrid.rowKeys;
  const displayedMonthTotals = useMemo(
    () =>
      workspace.months.map((month) => ({
        month,
        amount: Number(
          visibleRows
            .reduce((sum, row) => {
              const cell = getRowCell(row, month);
              const draft = editorState.drafts[row.rowKey] ?? buildDraft(row);
              return sum + Number(getDisplayCellValue(cell, draft));
            }, 0)
            .toFixed(2),
        ),
      })),
    [editorState.drafts, visibleRows, workspace.months],
  );
  const activeSelectedMonth = cellSelection?.focusMonth ?? null;
  const activeSelectedRow =
    cellSelection?.focusRowKey ? rowsByKey[cellSelection.focusRowKey] ?? null : selectedRow;
  const activeSelectedCell =
    activeSelectedRow && activeSelectedMonth
      ? getRowCell(activeSelectedRow, activeSelectedMonth)
      : null;
  const activeSelectedDraft =
    activeSelectedRow
      ? editorState.drafts[activeSelectedRow.rowKey] ?? buildDraft(activeSelectedRow)
      : undefined;
  const activeSelectedDraftCell =
    activeSelectedCell && activeSelectedDraft
      ? toDraftCell(
          getDisplayCellValue(activeSelectedCell, activeSelectedDraft),
          getCellLockValue(activeSelectedCell, activeSelectedDraft),
        )
      : null;

  function updateFilters(nextFilters: PhasingFilters) {
    const nextSearch = serializeFilters(nextFilters);
    startTransition(() => {
      router.replace(nextSearch ? `${pathname}?${nextSearch}` : pathname);
    });
  }

  function readDraft(row: ForecastPhasingWorkspaceRead["rows"][number]): RowDraft {
    return editorState.drafts[row.rowKey] ?? buildDraft(row);
  }

  function commitDraftChange(
    row: ForecastPhasingWorkspaceRead["rows"][number],
    updater: (draft: RowDraft) => RowDraft,
    options?: {
      recordHistory?: boolean;
      resetHistory?: boolean;
    },
  ) {
    setEditorState((current) => {
      const currentDraft = current.drafts[row.rowKey] ?? buildDraft(row);
      const nextDraft = updater(cloneRowDraft(currentDraft));
      const currentHistory = current.histories[row.rowKey] ?? buildDraftHistory(row);

      if (draftsEqual(currentDraft, nextDraft)) {
        if (
          options?.resetHistory &&
          (currentHistory.past.length > 0 || currentHistory.future.length > 0)
        ) {
          return {
            ...current,
            drafts: {
              ...current.drafts,
              [row.rowKey]: nextDraft,
            },
            histories: {
              ...current.histories,
              [row.rowKey]: getEmptyDraftHistory(),
            },
            draftUpdatedAts: {
              ...current.draftUpdatedAts,
              [row.rowKey]: buildDraftUpdatedAt(row),
            },
          };
        }
        return current;
      }

      return {
        ...current,
        drafts: {
          ...current.drafts,
          [row.rowKey]: nextDraft,
        },
        histories: {
          ...current.histories,
          [row.rowKey]: options?.resetHistory
            ? getEmptyDraftHistory()
            : options?.recordHistory === false
              ? currentHistory
              : {
                  past: [...currentHistory.past, cloneRowDraft(currentDraft)],
                  future: [],
                },
        },
        draftUpdatedAts: {
          ...current.draftUpdatedAts,
          [row.rowKey]: current.draftUpdatedAts[row.rowKey] ?? buildDraftUpdatedAt(row),
        },
      };
    });
  }

  function ensureDraft(row: ForecastPhasingWorkspaceRead["rows"][number]) {
    setEditorState((current) => {
      if (current.drafts[row.rowKey]) {
        return current;
      }
      return {
        ...current,
        drafts: {
          ...current.drafts,
          [row.rowKey]: buildDraft(row),
        },
        histories: {
          ...current.histories,
          [row.rowKey]: current.histories[row.rowKey] ?? buildDraftHistory(row),
        },
        saveModes: {
          ...current.saveModes,
          [row.rowKey]: current.saveModes[row.rowKey] ?? buildDraftSaveMode(row),
        },
        draftUpdatedAts: {
          ...current.draftUpdatedAts,
          [row.rowKey]: current.draftUpdatedAts[row.rowKey] ?? buildDraftUpdatedAt(row),
        },
      };
    });
  }

  function setSaveMode(row: ForecastPhasingWorkspaceRead["rows"][number], saveMode: SaveMode) {
    setEditorState((current) => ({
      ...current,
      saveModes: {
        ...current.saveModes,
        [row.rowKey]: saveMode,
      },
      draftUpdatedAts: {
        ...current.draftUpdatedAts,
        [row.rowKey]: current.draftUpdatedAts[row.rowKey] ?? buildDraftUpdatedAt(row),
      },
    }));
    scheduleDraftSync(row.rowKey);
  }

  function undoDraft(row: ForecastPhasingWorkspaceRead["rows"][number]) {
    setEditorState((current) => {
      const history = current.histories[row.rowKey] ?? buildDraftHistory(row);
      if (history.past.length === 0) {
        return current;
      }
      const currentDraft = current.drafts[row.rowKey] ?? buildDraft(row);
      const previousDraft = cloneRowDraft(history.past[history.past.length - 1]!);
      return {
        ...current,
        drafts: {
          ...current.drafts,
          [row.rowKey]: previousDraft,
        },
        histories: {
          ...current.histories,
          [row.rowKey]: {
            past: history.past.slice(0, -1),
            future: [cloneRowDraft(currentDraft), ...history.future],
          },
        },
        draftUpdatedAts: {
          ...current.draftUpdatedAts,
          [row.rowKey]: current.draftUpdatedAts[row.rowKey] ?? buildDraftUpdatedAt(row),
        },
      };
    });
    scheduleDraftSync(row.rowKey);
  }

  function redoDraft(row: ForecastPhasingWorkspaceRead["rows"][number]) {
    setEditorState((current) => {
      const history = current.histories[row.rowKey] ?? buildDraftHistory(row);
      const nextDraft = history.future[0];
      if (!nextDraft) {
        return current;
      }
      const currentDraft = current.drafts[row.rowKey] ?? buildDraft(row);
      return {
        ...current,
        drafts: {
          ...current.drafts,
          [row.rowKey]: cloneRowDraft(nextDraft),
        },
        histories: {
          ...current.histories,
          [row.rowKey]: {
            past: [...history.past, cloneRowDraft(currentDraft)],
            future: history.future.slice(1),
          },
        },
        draftUpdatedAts: {
          ...current.draftUpdatedAts,
          [row.rowKey]: current.draftUpdatedAts[row.rowKey] ?? buildDraftUpdatedAt(row),
        },
      };
    });
    scheduleDraftSync(row.rowKey);
  }

  async function refreshWorkspaceSnapshot(): Promise<ForecastPhasingWorkspaceRead> {
    return queryClient.fetchQuery({
      queryKey: queryKeys.forecastPhasingWorkspace(filtersKey),
      queryFn: async () => api.getForecastPhasingWorkspace(toWorkspaceQueryOptions(queryFilters)),
    });
  }

  async function syncDraftRow(
    rowKey: string,
    rowOverride?: ForecastPhasingWorkspaceRead["rows"][number],
    stateOverride?: DraftSyncState,
  ) {
    const row = rowOverride ?? rowsByKeyRef.current[rowKey];
    if (!row) {
      return;
    }
    const currentEditorState = editorStateRef.current;
    const currentDraft =
      stateOverride?.draft ?? (currentEditorState.drafts[row.rowKey] ?? buildDraft(row));
    const currentHistory =
      stateOverride?.history ??
      (currentEditorState.histories[row.rowKey] ?? buildDraftHistory(row));
    const currentSaveMode =
      stateOverride?.saveMode ??
      (currentEditorState.saveModes[row.rowKey] ?? buildDraftSaveMode(row));
    const expectedDraftUpdatedAt =
      stateOverride?.draftUpdatedAt ??
      (currentEditorState.draftUpdatedAts[row.rowKey] ?? buildDraftUpdatedAt(row));

    setSyncingRowKeys((current) => ({
      ...current,
      [rowKey]: true,
    }));
    try {
      const syncedDraft = await api.updateProjectForecastPhasingDraft(row.projectId, {
        rowMode: row.rowMode,
        disciplineId: row.disciplineId ?? null,
        saveMode: currentSaveMode,
        expectedDraftUpdatedAt,
        currentState: buildDraftStatePayload(currentDraft),
        pastStates: currentHistory.past.map((state) => buildDraftStatePayload(state)),
        futureStates: currentHistory.future.map((state) => buildDraftStatePayload(state)),
      });
      setEditorState((current) => ({
        ...current,
        drafts: {
          ...current.drafts,
          [rowKey]: buildDraftFromState(syncedDraft.currentState),
        },
        histories: {
          ...current.histories,
          [rowKey]: {
            past: (syncedDraft.pastStates ?? []).map((state: ForecastPhasingDraftStateRead) =>
              buildDraftFromState(state),
            ),
            future: (syncedDraft.futureStates ?? []).map((state: ForecastPhasingDraftStateRead) =>
              buildDraftFromState(state),
            ),
          },
        },
        saveModes: {
          ...current.saveModes,
          [rowKey]: syncedDraft.saveMode === "merge" ? "merge" : "replace",
        },
        draftUpdatedAts: {
          ...current.draftUpdatedAts,
          [rowKey]: syncedDraft.updatedAt,
        },
      }));
      setDraftSyncErrors((current) => ({
        ...current,
        [rowKey]: null,
      }));
      setDraftConflicts((current) => ({
        ...current,
        [rowKey]: null,
      }));
    } catch (caughtError: unknown) {
      if (caughtError instanceof ApiClientError && caughtError.status === 409) {
        setDraftConflicts((current) => ({
          ...current,
          [rowKey]: {
            baselineDraft: buildDraft(row),
            baselineSaveMode: buildDraftSaveMode(row),
            message: caughtError.message,
          },
        }));
        setDraftSyncErrors((current) => ({
          ...current,
          [rowKey]: null,
        }));
        try {
          await refreshWorkspaceSnapshot();
        } catch {
          setDraftSyncErrors((current) => ({
            ...current,
            [rowKey]:
              "The shared draft changed, and the latest version could not be reloaded yet.",
          }));
        }
        return;
      }
      const message =
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not persist the shared phasing draft.";
      setDraftSyncErrors((current) => ({
        ...current,
        [rowKey]: message,
      }));
    } finally {
      setSyncingRowKeys((current) => ({
        ...current,
        [rowKey]: false,
      }));
    }
  }

  function scheduleDraftSync(
    rowKey: string,
    immediate = false,
    rowOverride?: ForecastPhasingWorkspaceRead["rows"][number],
    stateOverride?: DraftSyncState,
  ) {
    const currentTimer = draftSyncTimersRef.current[rowKey];
    if (currentTimer) {
      window.clearTimeout(currentTimer);
      delete draftSyncTimersRef.current[rowKey];
    }
    if (immediate) {
      void syncDraftRow(rowKey, rowOverride, stateOverride);
      return;
    }
    draftSyncTimersRef.current[rowKey] = window.setTimeout(() => {
      delete draftSyncTimersRef.current[rowKey];
      void syncDraftRow(rowKey);
    }, 150);
  }

  async function discardSharedDraft(row: ForecastPhasingWorkspaceRead["rows"][number]) {
    const currentTimer = draftSyncTimersRef.current[row.rowKey];
    if (currentTimer) {
      window.clearTimeout(currentTimer);
      delete draftSyncTimersRef.current[row.rowKey];
    }
    const nextWorkspace = await api.discardProjectForecastPhasingDraft(row.projectId, {
      forecastVersionId: row.forecastVersionId ?? null,
      rowMode: row.rowMode,
      disciplineId: row.disciplineId ?? null,
    });
    setEditorState((current) => {
      const nextDrafts = { ...current.drafts };
      const nextHistories = { ...current.histories };
      const nextSaveModes = { ...current.saveModes };
      const nextDraftUpdatedAts = { ...current.draftUpdatedAts };
      delete nextDrafts[row.rowKey];
      delete nextHistories[row.rowKey];
      delete nextSaveModes[row.rowKey];
      delete nextDraftUpdatedAts[row.rowKey];
      return {
        drafts: nextDrafts,
        histories: nextHistories,
        saveModes: nextSaveModes,
        draftUpdatedAts: nextDraftUpdatedAts,
      };
    });
    setDraftSyncErrors((current) => ({
      ...current,
      [row.rowKey]: null,
    }));
    setDraftConflicts((current) => ({
      ...current,
      [row.rowKey]: null,
    }));
    await queryClient.setQueryData(
      queryKeys.forecastPhasingWorkspace(filtersKey),
      nextWorkspace,
    );
    await queryClient.invalidateQueries({
      queryKey: queryKeys.forecastPhasingWorkspace(filtersKey),
    });
  }

  function resetDraft(row: ForecastPhasingWorkspaceRead["rows"][number]) {
    void discardSharedDraft(row);
  }

  async function resolveDraftConflict(
    row: ForecastPhasingWorkspaceRead["rows"][number],
    strategy: "reload" | "merge",
  ) {
    const conflictState = draftConflicts[row.rowKey];
    if (!conflictState) {
      return;
    }
    setResolvingConflictRowKeys((current) => ({
      ...current,
      [row.rowKey]: true,
    }));
    try {
      const latestWorkspace = await refreshWorkspaceSnapshot();
      const latestRow = latestWorkspace.rows.find((item) => item.rowKey === row.rowKey);
      if (!latestRow) {
        setDraftSyncErrors((current) => ({
          ...current,
          [row.rowKey]: "The latest shared draft could not be found for this row.",
        }));
        return;
      }

      if (strategy === "reload") {
        setEditorState((current) => {
          const nextDrafts = { ...current.drafts };
          const nextHistories = { ...current.histories };
          const nextSaveModes = { ...current.saveModes };
          const nextDraftUpdatedAts = { ...current.draftUpdatedAts };
          delete nextDrafts[row.rowKey];
          delete nextHistories[row.rowKey];
          delete nextSaveModes[row.rowKey];
          delete nextDraftUpdatedAts[row.rowKey];
          return {
            drafts: nextDrafts,
            histories: nextHistories,
            saveModes: nextSaveModes,
            draftUpdatedAts: nextDraftUpdatedAts,
          };
        });
      } else {
        const currentEditorState = editorStateRef.current;
        const localDraft = currentEditorState.drafts[row.rowKey] ?? buildDraft(row);
        const localSaveMode =
          currentEditorState.saveModes[row.rowKey] ?? buildDraftSaveMode(row);
        const latestDraft = buildDraft(latestRow);
        const mergedDraft = mergeDraftOntoLatest(
          latestDraft,
          conflictState.baselineDraft,
          localDraft,
        );
        const latestHistory = buildDraftHistory(latestRow);
        const mergedSaveMode =
          localSaveMode !== conflictState.baselineSaveMode
            ? localSaveMode
            : buildDraftSaveMode(latestRow);
        const mergedHistory = draftsEqual(latestDraft, mergedDraft)
          ? latestHistory
          : {
              past: [...latestHistory.past, cloneRowDraft(latestDraft)],
              future: [],
            };
        const latestDraftUpdatedAt = buildDraftUpdatedAt(latestRow);

        setEditorState((current) => ({
          ...current,
          drafts: {
            ...current.drafts,
            [row.rowKey]: mergedDraft,
          },
          histories: {
            ...current.histories,
            [row.rowKey]: mergedHistory,
          },
          saveModes: {
            ...current.saveModes,
            [row.rowKey]: mergedSaveMode,
          },
          draftUpdatedAts: {
            ...current.draftUpdatedAts,
            [row.rowKey]: latestDraftUpdatedAt,
          },
        }));
        scheduleDraftSync(row.rowKey, true, latestRow, {
          draft: mergedDraft,
          history: mergedHistory,
          saveMode: mergedSaveMode,
          draftUpdatedAt: latestDraftUpdatedAt,
        });
      }

      setDraftConflicts((current) => ({
        ...current,
        [row.rowKey]: null,
      }));
      setDraftSyncErrors((current) => ({
        ...current,
        [row.rowKey]: null,
      }));
    } catch (caughtError: unknown) {
      setDraftSyncErrors((current) => ({
        ...current,
        [row.rowKey]:
          caughtError instanceof ApiClientError
            ? caughtError.message
            : "Could not resolve the shared draft conflict.",
      }));
    } finally {
      setResolvingConflictRowKeys((current) => ({
        ...current,
        [row.rowKey]: false,
      }));
    }
  }

  function getRowCell(
    row: ForecastPhasingWorkspaceRead["rows"][number],
    month: string,
  ): ForecastPhasingCellRead {
    return (
      (row.cells ?? []).find((item) => item.month === month) ??
      ({
        month,
        amount: 0,
        weightedAmount: 0,
        editable: true,
        isLocked: false,
        isManualOverride: false,
      } as ForecastPhasingCellRead)
    );
  }

  function applyMonthsToDraft(
    row: ForecastPhasingWorkspaceRead["rows"][number],
    monthsToApply: string[],
    updater: (
      currentCell: DraftCell,
      month: string,
      baseCell: ForecastPhasingCellRead,
    ) => DraftCell,
  ) {
    if (monthsToApply.length === 0) {
      return;
    }
    commitDraftChange(row, (draft) => {
      const nextDraft = cloneRowDraft(draft);
      monthsToApply.forEach((month) => {
        const baseCell = getRowCell(row, month);
        if (!row.canEdit || !baseCell.editable) {
          return;
        }
        const currentCell =
          nextDraft.cells[month] ?? toDraftCell(String(baseCell.amount), baseCell.isLocked);
        nextDraft.cells[month] = updater(currentCell, month, baseCell);
      });
      return nextDraft;
    });
    scheduleDraftSync(row.rowKey);
  }

  function applyGridSelection(
    selection: CellSelection | null,
    updater: (
      row: ForecastPhasingWorkspaceRead["rows"][number],
      currentCell: DraftCell,
      month: string,
      baseCell: ForecastPhasingCellRead,
      rowOffset: number,
      monthOffset: number,
    ) => DraftCell,
  ) {
    const grid = buildSelectedGrid(selection, visibleRowKeys, workspace.months);
    if (!grid.cells.length) {
      return;
    }
    const monthsByRowKey = new Map<string, Array<{ month: string; monthOffset: number; rowOffset: number }>>();
    grid.cells.forEach((item) => {
      const current = monthsByRowKey.get(item.rowKey) ?? [];
      current.push(item);
      monthsByRowKey.set(item.rowKey, current);
    });

    monthsByRowKey.forEach((items, rowKey) => {
      const row = rowsByKey[rowKey];
      if (!row) {
        return;
      }
      commitDraftChange(row, (draft) => {
        const nextDraft = cloneRowDraft(draft);
        items.forEach(({ month, monthOffset, rowOffset }) => {
          const baseCell = getRowCell(row, month);
          if (!row.canEdit || !baseCell.editable) {
            return;
          }
          const currentCell =
            nextDraft.cells[month] ?? toDraftCell(String(baseCell.amount), baseCell.isLocked);
          nextDraft.cells[month] = updater(
            row,
            currentCell,
            month,
            baseCell,
            rowOffset,
            monthOffset,
          );
        });
        return nextDraft;
      });
      scheduleDraftSync(row.rowKey);
    });
  }

  function parseClipboardMatrix(text: string): string[][] {
    return text
      .replace(/\r\n/g, "\n")
      .split("\n")
      .filter((row) => row.length > 0)
      .map((row) => row.split("\t"));
  }

  function applyClipboardMatrix(anchorRowKey: string, anchorMonth: string, matrix: string[][]) {
    const rowStart = visibleRowKeys.indexOf(anchorRowKey);
    const monthStart = workspace.months.indexOf(anchorMonth);
    if (rowStart < 0 || monthStart < 0 || matrix.length === 0) {
      return;
    }

    matrix.forEach((rowValues, rowOffset) => {
      const rowKey = visibleRowKeys[rowStart + rowOffset];
      if (!rowKey) {
        return;
      }
      const row = rowsByKey[rowKey];
      if (!row) {
        return;
      }
      commitDraftChange(row, (draft) => {
        const nextDraft = cloneRowDraft(draft);
        rowValues.forEach((rawValue, monthOffset) => {
          const month = workspace.months[monthStart + monthOffset];
          if (!month) {
            return;
          }
          const baseCell = getRowCell(row, month);
          if (!row.canEdit || !baseCell.editable) {
            return;
          }
          const parsedAmount = Number(rawValue.replace(/,/g, "").trim());
          if (!Number.isFinite(parsedAmount)) {
            return;
          }
          nextDraft.cells[month] = toDraftCell(String(parsedAmount), baseCell.isLocked);
        });
        return nextDraft;
      });
      scheduleDraftSync(row.rowKey);
    });
  }

  function selectCell(
    row: ForecastPhasingWorkspaceRead["rows"][number],
    month: string,
    extendSelection = false,
  ) {
    setSelectedRowKey(row.rowKey);
    ensureDraft(row);
    setCellSelection((current) => {
      if (extendSelection && current) {
        return {
          ...current,
          focusRowKey: row.rowKey,
          focusMonth: month,
        };
      }
      return {
        anchorRowKey: row.rowKey,
        anchorMonth: month,
        focusRowKey: row.rowKey,
        focusMonth: month,
      };
    });
  }

  function updateDraftCell(
    row: ForecastPhasingWorkspaceRead["rows"][number],
    cell: ForecastPhasingCellRead,
    patch: Partial<DraftCell>,
  ) {
    commitDraftChange(row, (draft) => ({
      ...draft,
      cells: {
        ...draft.cells,
        [cell.month]: toDraftCell(
          patch.amount ?? draft.cells[cell.month]?.amount ?? String(cell.amount),
          patch.isLocked ?? draft.cells[cell.month]?.isLocked ?? cell.isLocked,
        ),
      },
    }));
    scheduleDraftSync(row.rowKey);
  }

  function updateDraftReason(
    row: ForecastPhasingWorkspaceRead["rows"][number],
    reason: string,
  ) {
    commitDraftChange(row, (draft) => ({
      ...draft,
      reason,
    }));
    scheduleDraftSync(row.rowKey);
  }

  useEffect(() => {
    if (
      cellSelection &&
      (!rowsByKey[cellSelection.anchorRowKey] || !rowsByKey[cellSelection.focusRowKey])
    ) {
      setCellSelection(null);
    }
  }, [cellSelection, rowsByKey]);

  useEffect(() => {
    if (
      fillDragState &&
      (!rowsByKey[fillDragState.sourceSelection.anchorRowKey] ||
        !rowsByKey[fillDragState.sourceSelection.focusRowKey])
    ) {
      setFillDragState(null);
    }
  }, [fillDragState, rowsByKey]);

  useEffect(() => {
    if (!fillDragState) {
      return undefined;
    }
    const currentFillDrag = fillDragState;
    const sourceGrid = buildSelectedGrid(
      currentFillDrag.sourceSelection,
      visibleRowKeys,
      workspace.months,
    );
    const sourceRowCount = Math.max(sourceGrid.rowKeys.length, 1);
    const sourceMonthCount = Math.max(sourceGrid.months.length, 1);

    function finishFillDrag() {
      const targetSelection = cellSelection ?? currentFillDrag.sourceSelection;
      if (currentFillDrag.sourceCells.length) {
        applyGridSelection(targetSelection, (_row, _currentCell, _month, _baseCell, rowOffset, monthOffset) => {
          const patternCell =
            currentFillDrag.sourceCells.find(
              (item) =>
                item.rowOffset === rowOffset % sourceRowCount &&
                item.monthOffset === monthOffset % sourceMonthCount,
            ) ?? currentFillDrag.sourceCells[0];
          return patternCell ? toDraftCell(patternCell.value.amount, patternCell.value.isLocked) : toDraftCell("0", false);
        });
      }
      setFillDragState(null);
    }

    window.addEventListener("mouseup", finishFillDrag);
    return () => {
      window.removeEventListener("mouseup", finishFillDrag);
    };
  }, [applyGridSelection, cellSelection, fillDragState, visibleRowKeys, workspace.months]);

  useEffect(() => {
    return () => {
      Object.values(draftSyncTimersRef.current).forEach((timer) => {
        window.clearTimeout(timer);
      });
      draftSyncTimersRef.current = {};
    };
  }, []);

  const saveMutation = useMutation({
    mutationFn: async (row: ForecastPhasingWorkspaceRead["rows"][number]) => {
      const currentTimer = draftSyncTimersRef.current[row.rowKey];
      if (currentTimer) {
        window.clearTimeout(currentTimer);
        delete draftSyncTimersRef.current[row.rowKey];
      }
      const draft = readDraft(row);
      return api.updateProjectForecastPhasing(row.projectId, {
        forecastVersionId: draft.forecastVersionId ?? null,
        expectedUpdatedAt: draft.expectedUpdatedAt,
        rowMode: row.rowMode,
        disciplineId: row.disciplineId ?? null,
        cells: Object.entries(draft.cells).map(([month, value]) => ({
          month,
          amount: Number(value.amount),
          isLocked: value.isLocked,
        })),
        replaceExistingOverrides:
          (editorState.saveModes[row.rowKey] ?? buildDraftSaveMode(row)) === "replace",
        sourceMethod: "manual_cells",
        reason: draft.reason || null,
      });
    },
    onSuccess: async (_workspace, row) => {
      setEditorState((current) => {
        const nextDrafts = { ...current.drafts };
        const nextHistories = { ...current.histories };
        const nextSaveModes = { ...current.saveModes };
        const nextDraftUpdatedAts = { ...current.draftUpdatedAts };
        delete nextDrafts[row.rowKey];
        delete nextHistories[row.rowKey];
        delete nextSaveModes[row.rowKey];
        delete nextDraftUpdatedAts[row.rowKey];
        return {
          drafts: nextDrafts,
          histories: nextHistories,
          saveModes: nextSaveModes,
          draftUpdatedAts: nextDraftUpdatedAts,
        };
      });
      const currentTimer = draftSyncTimersRef.current[row.rowKey];
      if (currentTimer) {
        window.clearTimeout(currentTimer);
        delete draftSyncTimersRef.current[row.rowKey];
      }
      setDraftSyncErrors((current) => ({
        ...current,
        [row.rowKey]: null,
      }));
      setDraftConflicts((current) => ({
        ...current,
        [row.rowKey]: null,
      }));
      setCellSelection((current) =>
        current &&
        (current.anchorRowKey === row.rowKey || current.focusRowKey === row.rowKey)
          ? null
          : current,
      );
      await queryClient.invalidateQueries({
        queryKey: queryKeys.forecastPhasingWorkspace(filtersKey),
      });
    },
  });

  const previewMutation = useMutation({
    mutationFn: async ({
      row,
      action,
      cadenceProfileType,
    }: {
      row: ForecastPhasingWorkspaceRead["rows"][number];
      action: string;
      cadenceProfileType?: string;
    }) => {
      const draft = readDraft(row);
      return api.previewForecastPhasingAction({
        action,
        cadenceProfileType: cadenceProfileType ?? null,
        disciplineId: row.disciplineId ?? null,
        fromMonth: filters.fromMonth,
        projectId: row.projectId,
        rowMode: row.rowMode,
        toMonth: filters.toMonth,
        lockedMonths: Object.entries(draft.cells)
          .filter(([, value]) => value.isLocked)
          .map(([month]) => month),
      });
    },
    onSuccess: (preview, variables) => {
      const row = variables.row;
      commitDraftChange(row, (baseDraft) => {
        const preservedLocked = Object.fromEntries(
          Object.entries(baseDraft.cells).filter(([, value]) => value.isLocked),
        );
        return {
          ...baseDraft,
          cells: {
            ...preservedLocked,
            ...Object.fromEntries(
              (preview.cells ?? []).map((cell) => [
                cell.month,
                toDraftCell(String(cell.amount), cell.isLocked),
              ]),
            ),
          },
        };
      });
      scheduleDraftSync(row.rowKey);
    },
  });

  function renderDataRow(row: ForecastPhasingWorkspaceRead["rows"][number]) {
    const rowCells = row.cells ?? [];
    const draft = readDraft(row);
    const selected = row.rowKey === selectedRowKey;
    const hasDraftConflict = Boolean(draftConflicts[row.rowKey]);

    return (
      <tr
        className={cn(
          "border-b border-slate-200 align-top",
          selected ? "bg-amber-50/60" : "bg-white",
        )}
        key={row.rowKey}
      >
        <td className="sticky left-0 z-10 border-r border-slate-200 bg-inherit px-3 py-3">
          <button
            className="w-full text-left"
            onClick={() => {
              setSelectedRowKey(row.rowKey);
              ensureDraft(row);
            }}
            type="button"
          >
            <p className="font-medium text-slate-900">{row.projectName}</p>
            <p className="text-xs text-slate-500">
              {row.disciplineName ?? "Project total"}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <StatusBadge value={row.status} />
              {rowCells.some((cell) => cell.isManualOverride) ? (
                <span className="rounded-full bg-amber-100 px-2 py-1 text-amber-900">
                  Override
                </span>
              ) : null}
              {hasDraftConflict ? (
                <span className="rounded-full bg-rose-100 px-2 py-1 text-rose-900">
                  Conflict
                </span>
              ) : null}
              {row.activeDraft ? (
                <span className="rounded-full bg-sky-100 px-2 py-1 text-sky-900">
                  Shared draft
                </span>
              ) : null}
            </div>
          </button>
        </td>
        <td className="sticky left-[240px] z-10 border-r border-slate-200 bg-inherit px-3 py-3 text-xs text-slate-600">
          <p>{row.clientName ?? "No client"}</p>
          <p>
            {row.executionStartDate
              ? formatMonthLabel(row.executionStartDate.slice(0, 7))
              : "No start"}
            {" → "}
            {row.executionEndDate
              ? formatMonthLabel(row.executionEndDate.slice(0, 7))
              : "No end"}
          </p>
          <p>{formatStatusLabel(row.basePhasingProfile ?? "not_set")}</p>
        </td>
        {workspace.months.map((month) => {
          const cell = getRowCell(row, month);
          const displayValue = getDisplayCellValue(cell, draft);
          const lockValue = getCellLockValue(cell, draft);
          const canEdit = row.canEdit && cell.editable;
          const isSelectedCell =
            selectedRowKeys.includes(row.rowKey) && selectedMonths.includes(month);
          const isActiveCell =
            cellSelection?.focusRowKey === row.rowKey && cellSelection.focusMonth === month;
          const isPendingOverride =
            draft.cells[month] !== undefined && isEffectiveDraftCell(draft.cells[month]);

          return (
            <td
              className={cn(
                "min-w-[132px] border-r border-slate-200 px-2 py-3",
                cell.actualAmount ? "bg-emerald-50/70" : "",
                cell.isManualOverride || isPendingOverride ? "bg-amber-50/70" : "",
                isSelectedCell ? "bg-sky-50/80 ring-2 ring-inset ring-sky-300" : "",
              )}
              onMouseEnter={() => {
                if (fillDragState && canEdit) {
                  setCellSelection({
                    anchorRowKey: fillDragState.sourceSelection.anchorRowKey,
                    anchorMonth: fillDragState.sourceSelection.anchorMonth,
                    focusRowKey: row.rowKey,
                    focusMonth: month,
                  });
                }
              }}
              key={`${row.rowKey}:${month}`}
            >
              {canEdit ? (
                <div className="relative space-y-2">
                  <input
                    className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                    data-testid={`phasing-input-${row.rowKey}-${month}`}
                    onChange={(event) => updateDraftCell(row, cell, { amount: event.target.value })}
                    onMouseDown={(event) => {
                      pendingCellFocusRef.current = {
                        rowKey: row.rowKey,
                        month,
                        extendSelection: event.shiftKey,
                      };
                    }}
                    onClick={(event) => {
                      pendingCellFocusRef.current = null;
                      selectCell(row, month, event.shiftKey);
                    }}
                    onFocus={() => {
                      const pendingCellFocus = pendingCellFocusRef.current;
                      if (
                        pendingCellFocus &&
                        pendingCellFocus.rowKey === row.rowKey &&
                        pendingCellFocus.month === month
                      ) {
                        if (pendingCellFocus.extendSelection) {
                          return;
                        }
                        pendingCellFocusRef.current = null;
                      }
                      selectCell(row, month);
                    }}
                    onPaste={(event) => {
                      const matrix = parseClipboardMatrix(
                        event.clipboardData.getData("text/plain"),
                      );
                      if (!matrix.length) {
                        return;
                      }
                      event.preventDefault();
                      const selectionIncludesCell =
                        selectedRowKeys.includes(row.rowKey) && selectedMonths.includes(month);
                      const targetSelection =
                        selectionIncludesCell && cellSelection
                          ? cellSelection
                          : {
                              anchorRowKey: row.rowKey,
                              anchorMonth: month,
                              focusRowKey: row.rowKey,
                              focusMonth: month,
                            };
                      if (
                        matrix.length === 1 &&
                        (matrix[0]?.length ?? 0) === 1 &&
                        selectionIncludesCell &&
                        selectedGrid.cells.length > 1
                      ) {
                        const pastedValue = matrix[0]?.[0] ?? "0";
                        const parsedAmount = Number(pastedValue.replace(/,/g, "").trim());
                        if (!Number.isFinite(parsedAmount)) {
                          return;
                        }
                        applyGridSelection(targetSelection, (_targetRow, _currentCell, _targetMonth, baseCell) =>
                          toDraftCell(String(parsedAmount), baseCell.isLocked),
                        );
                        return;
                      }
                      applyClipboardMatrix(targetSelection.anchorRowKey, targetSelection.anchorMonth, matrix);
                    }}
                    type="number"
                    value={displayValue}
                  />
                  <label className="flex items-center gap-2 text-[11px] text-slate-600">
                    <input
                      checked={lockValue}
                      onChange={(event) =>
                        updateDraftCell(row, cell, { isLocked: event.target.checked })
                      }
                      type="checkbox"
                    />
                    Lock
                  </label>
                  {isActiveCell ? (
                    <button
                      aria-label={`Drag fill from ${formatMonthLabel(month)}`}
                      className="absolute bottom-1 right-1 h-3 w-3 rounded-sm border border-slate-500 bg-slate-900"
                      data-testid={`phasing-fill-handle-${row.rowKey}-${month}`}
                      onMouseDown={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        const sourceSelection =
                          selectedRowKeys.includes(row.rowKey) &&
                          selectedMonths.includes(month) &&
                          cellSelection
                            ? cellSelection
                            : {
                                anchorRowKey: row.rowKey,
                                anchorMonth: month,
                                focusRowKey: row.rowKey,
                                focusMonth: month,
                              };
                        const sourceGrid = buildSelectedGrid(
                          sourceSelection,
                          visibleRowKeys,
                          workspace.months,
                        );
                        setFillDragState({
                          sourceSelection,
                          sourceCells: sourceGrid.cells.map((sourceCell) => {
                            const sourceRow = rowsByKey[sourceCell.rowKey];
                            const sourceBaseCell = sourceRow
                              ? getRowCell(sourceRow, sourceCell.month)
                              : cell;
                            const sourceDraft = sourceRow ? readDraft(sourceRow) : draft;
                            return {
                              rowOffset: sourceCell.rowOffset,
                              monthOffset: sourceCell.monthOffset,
                              value: toDraftCell(
                                getDisplayCellValue(sourceBaseCell, sourceDraft),
                                getCellLockValue(sourceBaseCell, sourceDraft),
                              ),
                            };
                          }),
                        });
                        setCellSelection(sourceSelection);
                      }}
                      type="button"
                    />
                  ) : null}
                </div>
              ) : (
                <div className="space-y-1">
                  <p className="text-sm font-medium text-slate-900">
                    {formatCurrency(Number(displayValue), row.currencyCode)}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    {cell.actualAmount
                      ? "Actual"
                      : cell.isManualOverride
                        ? lockValue
                          ? "Manual locked"
                          : "Manual"
                        : "Forecast"}
                  </p>
                </div>
              )}
            </td>
          );
        })}
        <td className="min-w-[140px] px-3 py-3 text-sm font-medium text-slate-900">
          {formatCurrency(row.totalAmount, row.currencyCode)}
        </td>
      </tr>
    );
  }

  return (
    <div className="space-y-6">
      <SectionCard
        title="Revenue Phasing Workspace"
        description="Spreadsheet-style monthly revenue planning built directly on the forecast version and monthly allocation model. This is the only editing surface for manual phasing overrides."
      >
        <div className="space-y-4">
          <div className="grid gap-3 xl:grid-cols-8">
            <label className="grid gap-1.5">
              <span className="text-sm font-medium text-slate-700">From month</span>
              <input
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                onChange={(event) =>
                  updateFilters({ ...filters, fromMonth: event.currentTarget.value })
                }
                type="month"
                value={filters.fromMonth}
              />
            </label>
            <label className="grid gap-1.5">
              <span className="text-sm font-medium text-slate-700">To month</span>
              <input
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                onChange={(event) =>
                  updateFilters({ ...filters, toMonth: event.currentTarget.value })
                }
                type="month"
                value={filters.toMonth}
              />
            </label>
            <SelectField
              label="Row mode"
              onChange={(event) =>
                updateFilters({
                  ...filters,
                  rowMode: event.currentTarget.value as RowMode,
                })
              }
              value={filters.rowMode}
            >
              <option value="project">Project</option>
              <option value="discipline">Project + discipline</option>
            </SelectField>
            <SelectField
              label="Client"
              onChange={(event) =>
                updateFilters({
                  ...filters,
                  clientId: event.currentTarget.value || undefined,
                })
              }
              value={filters.clientId ?? ""}
            >
              <option value="">All clients</option>
              {(workspace.filterOptions.clients ?? []).map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="Project"
              onChange={(event) =>
                updateFilters({
                  ...filters,
                  projectId: event.currentTarget.value || undefined,
                })
              }
              value={filters.projectId ?? ""}
            >
              <option value="">All projects</option>
              {(workspace.filterOptions.projects ?? []).map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="Discipline"
              onChange={(event) =>
                updateFilters({
                  ...filters,
                  disciplineId: event.currentTarget.value || undefined,
                })
              }
              value={filters.disciplineId ?? ""}
            >
              <option value="">All disciplines</option>
              {(workspace.filterOptions.disciplines ?? []).map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="Status"
              onChange={(event) =>
                updateFilters({
                  ...filters,
                  status: event.currentTarget.value || undefined,
                })
              }
              value={filters.status ?? ""}
            >
              <option value="">All statuses</option>
              {(workspace.filterOptions.statuses ?? []).map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="Scenario"
              onChange={(event) =>
                updateFilters({
                  ...filters,
                  scenarioKey: event.currentTarget.value || undefined,
                })
              }
              value={filters.scenarioKey ?? "base"}
            >
              {(workspace.filterOptions.scenarios ?? []).map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </SelectField>
          </div>
          <div className="flex items-center justify-between text-xs text-slate-500">
            <p>
              {workspace.rows.length} row{workspace.rows.length === 1 ? "" : "s"} loaded
            </p>
            <p>{isPending ? "Refreshing…" : "Live phasing data"}</p>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Status Trend"
        description="Monthly totals by project status over the current planning horizon."
      >
        <StatusTrendChart workspace={workspace} />
      </SectionCard>

      {selectedRow ? (
        <SectionCard
          title="Selected Row"
          description="Direct month edits become explicit manual overrides. Unedited months stay system-generated and continue to rebalance through the forecast engine."
        >
          <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-medium text-slate-900">
                  {selectedRow.projectName}
                  {selectedRow.disciplineName ? ` · ${selectedRow.disciplineName}` : ""}
                </p>
                <StatusBadge value={selectedRow.status} />
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                  {formatStatusLabel(selectedRow.basePhasingProfile ?? "not_set")}
                </span>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
                    Row total
                  </p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">
                    {formatCurrency(selectedRow.totalAmount, selectedRow.currencyCode)}
                  </p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
                    Manual months
                  </p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">
                    {countEffectiveDraftCells(selectedDraft)}
                  </p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
                    Remaining auto balance
                  </p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">
                    {formatCurrency(
                      Math.max(
                        0,
                        Number((selectedRow.totalAmount - sumManualDraftValues(selectedDraft)).toFixed(2)),
                      ),
                      selectedRow.currencyCode,
                    )}
                  </p>
                </div>
              </div>
              <TextAreaField
                label="Change reason"
                onChange={(event) => updateDraftReason(selectedRow, event.target.value)}
                placeholder="Why is the phasing changing?"
                value={selectedDraft?.reason ?? ""}
              />
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                <p className="font-medium text-slate-900">Cell selection</p>
                <p className="mt-1">
                  {selectedMonths.length
                    ? describeSelectionRange(selectedRowKeys.length, selectedMonths)
                    : "Select a month cell, shift-click across rows or months, paste a rectangular block, or drag the fill handle on the active selection."}
                </p>
                {selectedRow.activeDraft ? (
                  <p className="mt-1 text-xs text-slate-500">
                    Shared draft last synced {formatDateTime(selectedRow.activeDraft.updatedAt)}
                    {selectedRow.activeDraft.updatedByEmail
                      ? ` by ${selectedRow.activeDraft.updatedByEmail}`
                      : ""}
                  </p>
                ) : null}
              </div>
            </div>
            <div className="space-y-3">
              <SelectField
                label="Base phasing profile preview"
                onChange={(event) => setPreviewProfileType(event.currentTarget.value)}
                value={previewProfileType}
              >
                <option value="flat_equal">Flat / equal</option>
                <option value="front_loaded">Front-loaded</option>
                <option value="back_loaded">Back-loaded</option>
                <option value="mid_loaded">Mid-loaded</option>
                <option value="milestone_based">Milestone-based</option>
                <option value="episodic">Episodic</option>
                <option value="discipline_sequenced">Discipline-sequenced</option>
              </SelectField>
              <div className="flex flex-wrap gap-2">
                <Button
                  onClick={() =>
                    previewMutation.mutate({ row: selectedRow, action: "equal_split" })
                  }
                  type="button"
                  variant="secondary"
                >
                  Equal split
                </Button>
                <Button
                  onClick={() =>
                    previewMutation.mutate({ row: selectedRow, action: "rebalance_remaining" })
                  }
                  type="button"
                  variant="secondary"
                >
                  Rebalance
                </Button>
                <Button
                  onClick={() =>
                    previewMutation.mutate({
                      row: selectedRow,
                      action: "cadence_profile",
                      cadenceProfileType: previewProfileType,
                    })
                  }
                  type="button"
                  variant="secondary"
                >
                  Apply profile
                </Button>
                <Button
                  onClick={() => {
                    commitDraftChange(selectedRow, (draft) => ({
                      ...draft,
                      cells: {},
                    }));
                    scheduleDraftSync(selectedRow.rowKey);
                  }}
                  type="button"
                >
                  Clear overrides
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  data-testid="phasing-undo"
                  disabled={selectedHistory.past.length === 0}
                  onClick={() => undoDraft(selectedRow)}
                  type="button"
                  variant="secondary"
                >
                  Undo
                </Button>
                <Button
                  data-testid="phasing-redo"
                  disabled={selectedHistory.future.length === 0}
                  onClick={() => redoDraft(selectedRow)}
                  type="button"
                  variant="secondary"
                >
                  Redo
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={!selectedMonths.length || !activeSelectedDraftCell}
                  onClick={() => {
                    if (!activeSelectedDraftCell) {
                      return;
                    }
                    applyGridSelection(cellSelection, () =>
                      toDraftCell(
                        activeSelectedDraftCell.amount,
                        activeSelectedDraftCell.isLocked,
                      ),
                    );
                  }}
                  type="button"
                  variant="secondary"
                >
                  Fill selection
                </Button>
                <Button
                  data-testid="phasing-clear-selection"
                  disabled={!selectedGrid.cells.length}
                  onClick={() =>
                    applyGridSelection(cellSelection, () =>
                      toDraftCell("0", false),
                    )
                  }
                  type="button"
                  variant="secondary"
                >
                  Clear selection
                </Button>
                <Button
                  disabled={!selectedGrid.cells.length}
                  onClick={() =>
                    applyGridSelection(
                      cellSelection,
                      (_targetRow, currentCell) =>
                        toDraftCell(currentCell.amount, true),
                    )
                  }
                  type="button"
                  variant="secondary"
                >
                  Lock selection
                </Button>
                <Button
                  disabled={!selectedGrid.cells.length}
                  onClick={() =>
                    applyGridSelection(
                      cellSelection,
                      (_targetRow, currentCell) =>
                        toDraftCell(currentCell.amount, false),
                    )
                  }
                  type="button"
                  variant="secondary"
                >
                  Unlock selection
                </Button>
              </div>
              <SelectField
                data-testid="phasing-save-mode"
                label="Save mode"
                onChange={(event) =>
                  setSaveMode(selectedRow, event.currentTarget.value as SaveMode)
                }
                value={selectedSaveMode}
              >
                <option value="replace">Replace row overrides</option>
                <option value="merge">Merge with existing overrides</option>
              </SelectField>
              <p className="text-xs text-slate-500">
                Replace saves the current row draft as the full manual override set. Merge
                preserves untouched manual months already stored on the forecast version.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={
                    saveMutation.isPending ||
                    syncingRowKeys[selectedRow.rowKey] ||
                    !selectedRow.canEdit
                  }
                  onClick={() => saveMutation.mutate(selectedRow)}
                  type="button"
                  variant="primary"
                >
                  {saveMutation.isPending
                    ? "Saving…"
                    : syncingRowKeys[selectedRow.rowKey]
                      ? "Syncing draft…"
                      : "Save row"}
                </Button>
                <Button
                  onClick={() => resetDraft(selectedRow)}
                  type="button"
                >
                  Cancel changes
                </Button>
              </div>
            </div>
          </div>
          {previewMutation.error ? (
            <p className="mt-4 text-sm text-rose-700">
              {previewMutation.error instanceof ApiClientError
                ? previewMutation.error.message
                : "Could not generate the phasing preview."}
            </p>
          ) : null}
          {saveMutation.error ? (
            <p className="mt-4 text-sm text-rose-700">
              {saveMutation.error instanceof ApiClientError
                ? saveMutation.error.message
                : "Could not save phasing changes."}
            </p>
          ) : null}
          {selectedConflict ? (
            <div
              className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"
              data-testid="phasing-conflict-banner"
            >
              <p className="font-medium text-amber-950">
                Shared draft changed before your edits could sync.
              </p>
              <p className="mt-1">
                {selectedConflict.message} Reload the refreshed shared draft, or merge your{" "}
                {selectedConflictMonths.length} changed month
                {selectedConflictMonths.length === 1 ? "" : "s"} into it.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  data-testid="phasing-load-latest-draft"
                  disabled={resolvingConflictRowKeys[selectedRow.rowKey]}
                  onClick={() => resolveDraftConflict(selectedRow, "reload")}
                  type="button"
                  variant="secondary"
                >
                  {resolvingConflictRowKeys[selectedRow.rowKey]
                    ? "Reloading…"
                    : "Load latest draft"}
                </Button>
                <Button
                  data-testid="phasing-merge-conflict-draft"
                  disabled={resolvingConflictRowKeys[selectedRow.rowKey]}
                  onClick={() => resolveDraftConflict(selectedRow, "merge")}
                  type="button"
                  variant="primary"
                >
                  {resolvingConflictRowKeys[selectedRow.rowKey]
                    ? "Merging…"
                    : "Merge my edits"}
                </Button>
              </div>
            </div>
          ) : null}
          {draftSyncErrors[selectedRow.rowKey] ? (
            <p className="mt-4 text-sm text-rose-700">
              {draftSyncErrors[selectedRow.rowKey]}
            </p>
          ) : null}
        </SectionCard>
      ) : null}

      <SectionCard
        title="Planning Grid"
        description="Select a row to edit month cells directly. Actual months remain protected."
      >
        {workspaceQuery.error ? (
          <ErrorState
            description={
              workspaceQuery.error instanceof ApiClientError
                ? workspaceQuery.error.message
                : "Could not load the revenue phasing workspace."
            }
            title="Revenue phasing unavailable"
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-[0.12em] text-slate-500">
                  <th className="sticky left-0 z-20 min-w-[240px] border-r border-slate-200 bg-slate-50 px-3 py-3">
                    Row
                  </th>
                  <th className="sticky left-[240px] z-20 min-w-[180px] border-r border-slate-200 bg-slate-50 px-3 py-3">
                    Context
                  </th>
                  {workspace.months.map((month) => (
                    <th className="min-w-[132px] border-r border-slate-200 px-2 py-3" key={month}>
                      {formatMonthLabel(month)}
                    </th>
                  ))}
                  <th className="min-w-[140px] px-3 py-3">Total</th>
                </tr>
              </thead>
              <tbody>
                {filters.rowMode === "discipline"
                  ? groupedRows.map((group) => (
                      <Fragment key={group.projectId}>
                        <tr
                          className="border-b border-slate-200 bg-slate-100 text-sm text-slate-700"
                        >
                          <td className="sticky left-0 z-10 bg-slate-100 px-3 py-3" colSpan={2}>
                            <button
                              className="font-medium"
                              onClick={() =>
                                setCollapsedProjects((current) => ({
                                  ...current,
                                  [group.projectId]: !current[group.projectId],
                                }))
                              }
                              type="button"
                            >
                              {collapsedProjects[group.projectId] ? "+" : "−"} {group.projectName}
                            </button>
                          </td>
                          <td className="bg-slate-100 px-3 py-3 text-xs text-slate-500" colSpan={workspace.months.length + 1}>
                            {group.rows.length} discipline row{group.rows.length === 1 ? "" : "s"}
                          </td>
                        </tr>
                        {!collapsedProjects[group.projectId]
                          ? group.rows.map((row) => renderDataRow(row))
                          : null}
                      </Fragment>
                    ))
                  : workspace.rows.map((row) => renderDataRow(row))}
                <tr className="border-t border-slate-300 bg-slate-50 text-sm font-medium text-slate-900">
                  <td className="sticky left-0 z-10 bg-slate-50 px-3 py-3">Month totals</td>
                  <td className="sticky left-[240px] z-10 bg-slate-50 px-3 py-3 text-xs text-slate-500">
                    Visible rows only
                  </td>
                  {displayedMonthTotals.map((total) => (
                    <td className="border-r border-slate-200 px-2 py-3" key={`total:${total.month}`}>
                      {formatCurrency(total.amount, "GBP")}
                    </td>
                  ))}
                  <td className="px-3 py-3">
                    {formatCurrency(
                      displayedMonthTotals.reduce((sum, item) => sum + item.amount, 0),
                      "GBP",
                    )}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Recent Phasing Changes"
        description="Latest phasing edits recorded against the forecast version."
      >
        {(workspace.recentChanges ?? []).length ? (
          <div className="space-y-3">
            {(workspace.recentChanges ?? []).map((change) => (
              <div className="rounded-lg border border-slate-200 px-4 py-3" key={change.id}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm font-medium text-slate-900">
                    {change.projectId} · {formatMonthLabel(change.month)} · {formatStatusLabel(change.rowMode)}
                  </p>
                  <p className="text-xs text-slate-500">{formatDateTime(change.createdAt)}</p>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {change.actorEmail ?? "System"} · {formatStatusLabel(change.sourceMethod)}
                </p>
                <p className="mt-2 text-sm text-slate-700">
                  {formatCurrency(change.beforeAmount, "GBP")} → {formatCurrency(change.afterAmount, "GBP")}
                  {change.afterLocked ? " · locked" : ""}
                </p>
                {change.reason ? (
                  <p className="mt-1 text-xs text-slate-500">{change.reason}</p>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-600">No phasing edits have been recorded yet.</p>
        )}
      </SectionCard>
    </div>
  );
}
