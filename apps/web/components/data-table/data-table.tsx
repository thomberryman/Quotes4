import type { ReactNode } from "react";

import { cn } from "@/lib/classnames";
import type { TableColumn } from "@/lib/navigation/types";

interface DataTableProps<T> {
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  emptyState?: ReactNode;
  className?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  emptyState,
  className
}: DataTableProps<T>) {
  if (rows.length === 0) {
    return <>{emptyState ?? null}</>;
  }

  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead>
          <tr className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            {columns.map((column) => (
              <th key={column.key} className={cn("px-4 py-3", column.className)}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 bg-white">
          {rows.map((row) => (
            <tr key={rowKey(row)} className="align-top">
              {columns.map((column) => (
                <td key={column.key} className={cn("px-4 py-3 text-slate-700", column.className)}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
