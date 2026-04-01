import type { PropsWithChildren, ReactNode } from "react";

export function TableToolbar({
  children,
  actions
}: PropsWithChildren<{ actions?: ReactNode }>) {
  return (
    <div className="flex flex-col gap-3 border-b border-slate-200 px-5 py-4 md:flex-row md:items-center md:justify-between">
      <div className="flex flex-1 flex-wrap gap-3">{children}</div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}
