"use client";

import { useEffect, useState } from "react";

import { useQuery } from "@tanstack/react-query";

import { getBrowserApiClient } from "@/lib/api/browser-client";
import { queryKeys } from "@/lib/query/keys";

import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/error-state";

import {
  type DashboardFilters,
  type DashboardView,
  formatDrilldownTotalLabel,
  formatDrilldownValue,
  getDashboardCsvFileName,
  serializeDashboardFilters,
  toDashboardQueryOptions,
} from "./dashboard-helpers";

export function DrilldownDrawer({
  filters,
  onClose,
  view,
}: {
  filters: DashboardFilters;
  onClose: () => void;
  view: DashboardView | null;
}) {
  const api = getBrowserApiClient();
  const [isExporting, setIsExporting] = useState(false);
  const filtersKey = serializeDashboardFilters(filters);

  const drilldownQuery = useQuery({
    enabled: Boolean(view),
    placeholderData: (previousData) => previousData,
    queryFn: async () => {
      if (!view) {
        return null;
      }

      return api.getDashboardDrilldown(view, toDashboardQueryOptions(filters));
    },
    queryKey: view
      ? queryKeys.dashboardDrilldown(view, filtersKey)
      : ["dashboard-drilldown", "closed"],
  });
  const drilldown = drilldownQuery.data ?? null;

  useEffect(() => {
    if (!view) {
      return undefined;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, view]);

  if (!view) {
    return null;
  }

  async function handleExport() {
    if (!view) {
      return;
    }

    setIsExporting(true);

    try {
      const csv = await api.exportDashboardDrilldownCsv(
        view,
        toDashboardQueryOptions(filters),
      );
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = getDashboardCsvFileName(view, filters);
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/20">
      <button
        aria-label="Close drilldown"
        className="flex-1"
        onClick={onClose}
        type="button"
      />
      <aside
        aria-modal="true"
        className="relative flex h-full w-full max-w-4xl flex-col border-l border-slate-200 bg-white shadow-2xl"
        data-testid="dashboard-drilldown-drawer"
        role="dialog"
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
              Drilldown
            </p>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">
              {drilldown?.title ?? "Loading detail"}
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              Detail rows stay out of the main dashboard payload and are fetched
              only when you open a panel.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              data-testid="dashboard-export-csv"
              onClick={() => {
                void handleExport();
              }}
              type="button"
              variant="secondary"
            >
              {isExporting ? "Preparing CSV..." : "Export CSV"}
            </Button>
            <Button onClick={onClose} type="button" variant="ghost">
              Close
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {drilldownQuery.error ? (
            <ErrorState
              title="Drilldown unavailable"
              description="The detail rows could not be loaded for this dashboard view."
            />
          ) : null}

          {!drilldownQuery.data && drilldownQuery.isLoading ? (
            <div className="space-y-3">
              <div className="h-12 animate-pulse rounded-xl bg-slate-100" />
              <div className="h-12 animate-pulse rounded-xl bg-slate-100" />
              <div className="h-12 animate-pulse rounded-xl bg-slate-100" />
            </div>
          ) : null}

          {drilldown ? (
            <div className="space-y-5">
              {Object.entries(drilldown.totals).length > 0 ? (
                <div className="flex flex-wrap gap-3">
                  {Object.entries(drilldown.totals).map(([key, value]) => (
                    <div
                      className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
                      key={key}
                    >
                      <p className="text-xs uppercase tracking-wide text-slate-500">
                        {formatDrilldownTotalLabel(key)}
                      </p>
                      <p className="mt-1 text-sm font-medium text-slate-900">
                        {(() => {
                          const matchingColumn =
                            drilldown.columns.find((column) => column.key === key) ??
                            null;

                          return matchingColumn
                            ? formatDrilldownValue(matchingColumn, value)
                            : String(value ?? "—");
                        })()}
                      </p>
                    </div>
                  ))}
                </div>
              ) : null}

              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="min-w-full border-separate border-spacing-0 text-sm">
                  <thead className="sticky top-0 bg-white">
                    <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                      {drilldown.columns.map((column) => (
                        <th
                          className="border-b border-slate-200 px-4 py-3 font-medium"
                          key={column.key}
                        >
                          {column.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {drilldown.rows.map((row, index) => (
                      <tr
                        className={index % 2 === 0 ? "bg-white" : "bg-slate-50/60"}
                        key={`${drilldown.view}-${index}`}
                      >
                        {drilldown.columns.map((column) => (
                          <td
                            className="border-b border-slate-100 px-4 py-3 text-slate-700"
                            key={column.key}
                          >
                            {formatDrilldownValue(column, row[column.key])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="bg-slate-100 text-sm font-medium text-slate-900">
                      {drilldown.columns.map((column, index) => (
                        <td
                          className="border-t border-slate-200 px-4 py-3"
                          key={column.key}
                        >
                          {index === 0
                            ? "Totals"
                            : formatDrilldownValue(
                                column,
                                drilldown.totals[column.key] ?? null,
                              )}
                        </td>
                      ))}
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
