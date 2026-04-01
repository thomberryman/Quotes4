"use client";

import type { PropsWithChildren } from "react";
import { useState } from "react";

import { navigationGroups } from "@/lib/navigation/routes";
import type { WorkspaceDataMode } from "@/lib/workspace-config";

import { SidebarNav } from "./sidebar-nav";
import { TopBar } from "./top-bar";

export function AppShell({
  appDisplayName,
  userName,
  userEmail,
  workspaceDescription,
  workspaceLabel,
  workspaceMode,
  children
}: PropsWithChildren<{
  appDisplayName: string;
  userName: string;
  userEmail: string;
  workspaceDescription: string;
  workspaceLabel: string;
  workspaceMode: WorkspaceDataMode;
}>) {
  const [isNavOpen, setIsNavOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="grid min-h-screen lg:grid-cols-[290px_minmax(0,1fr)]">
        <aside className="hidden border-r border-slate-200 bg-slate-100 px-4 py-6 lg:block">
          <div className="mb-6 rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
            <p className="text-sm font-semibold text-slate-900">{workspaceLabel}</p>
            <p className="mt-2 text-sm text-slate-600">
              {workspaceDescription}
            </p>
          </div>
          <SidebarNav groups={navigationGroups} />
        </aside>

        {isNavOpen ? (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div
              className="absolute inset-0 bg-slate-950/30"
              onClick={() => setIsNavOpen(false)}
            />
            <aside className="relative h-full w-[310px] overflow-y-auto border-r border-slate-200 bg-slate-100 px-4 py-6 shadow-xl">
              <SidebarNav groups={navigationGroups} onNavigate={() => setIsNavOpen(false)} />
            </aside>
          </div>
        ) : null}

        <div className="min-w-0">
          <TopBar
            appDisplayName={appDisplayName}
            onOpenNav={() => setIsNavOpen(true)}
            userEmail={userEmail}
            userName={userName}
            workspaceLabel={workspaceLabel}
            workspaceMode={workspaceMode}
          />
          <main className="px-4 py-6 lg:px-6">
            <div className="mx-auto flex max-w-7xl flex-col gap-6">{children}</div>
          </main>
        </div>
      </div>
    </div>
  );
}
