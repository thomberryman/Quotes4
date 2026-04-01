import type { PropsWithChildren } from "react";

import { redirect } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { QueryProvider } from "@/components/providers/query-provider";
import { getServerApiClient } from "@/lib/api/server-client";
import { workspaceConfig } from "@/lib/workspace-config";

export default async function ShellLayout({ children }: PropsWithChildren) {
  const api = await getServerApiClient();
  const currentUser = await api.getCurrentUser().catch(() => null);
  if (!currentUser) {
    redirect("/login");
  }

  return (
    <QueryProvider>
      <AppShell
        appDisplayName={workspaceConfig.appDisplayName}
        userEmail={currentUser?.email ?? "Authenticated user"}
        userName={
          currentUser ? `${currentUser.firstName} ${currentUser.lastName}` : "Authenticated User"
        }
        workspaceDescription={workspaceConfig.workspaceDescription}
        workspaceLabel={workspaceConfig.workspaceLabel}
        workspaceMode={workspaceConfig.dataMode}
      >
        {children}
      </AppShell>
    </QueryProvider>
  );
}
