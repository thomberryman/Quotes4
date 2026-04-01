import { cn } from "@/lib/classnames";

import type { WorkspaceDataMode } from "@/lib/workspace-config";

import { LogoutButton } from "./logout-button";

export function TopBar({
  appDisplayName,
  userName,
  userEmail,
  workspaceLabel,
  workspaceMode,
  onOpenNav
}: {
  appDisplayName: string;
  userName: string;
  userEmail: string;
  workspaceLabel: string;
  workspaceMode: WorkspaceDataMode;
  onOpenNav?: () => void;
}) {
  return (
    <header className="sticky top-0 z-20 flex items-center justify-between border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur lg:px-6">
      <div className="flex items-center gap-3">
        {onOpenNav ? (
          <button
            className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-slate-200 text-slate-700 lg:hidden"
            onClick={onOpenNav}
            type="button"
          >
            Menu
          </button>
        ) : null}
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-slate-900">{appDisplayName}</p>
            <span
              className={cn(
                "inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.14em]",
                workspaceMode === "live"
                  ? "border-amber-300 bg-amber-50 text-amber-900"
                  : "border-sky-200 bg-sky-50 text-sky-900",
              )}
            >
              {workspaceLabel}
            </span>
          </div>
          <p className="text-xs text-slate-500">Operational quoting and forecasting workspace</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <div className="hidden text-right sm:block">
          <p className="text-sm font-medium text-slate-900">{userName}</p>
          <p className="text-xs text-slate-500">{userEmail}</p>
        </div>
        <LogoutButton />
      </div>
    </header>
  );
}
