import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { LoginForm } from "@/components/features/auth/login-form";
import { SectionCard } from "@/components/ui/section-card";
import { ACCESS_TOKEN_COOKIE_NAME } from "@/lib/api/access-token";
import { workspaceConfig } from "@/lib/workspace-config";

export default async function LoginPage() {
  const cookieStore = await cookies();
  if (cookieStore.get(ACCESS_TOKEN_COOKIE_NAME)?.value) {
    redirect("/dashboard");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl items-center px-4 py-10 lg:px-6">
      <div className="grid w-full gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <SectionCard
          description={workspaceConfig.productDescription}
          title={workspaceConfig.appDisplayName}
        >
          <div className="grid gap-4">
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-4">
              <p className="text-sm font-semibold text-slate-900">
                What is live now
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
                <li>Clients and contacts directories</li>
                <li>Projects, quote builder, and quote comparison</li>
                <li>
                  Forecast editing, comparable-project analysis, and quote vs
                  actual review
                </li>
                <li>
                  PDF ingestion review, CETA reconciliation, and dashboard queue
                  health
                </li>
              </ul>
            </div>
            <div
              className={`rounded-lg border px-4 py-4 ${
                workspaceConfig.dataMode === "live"
                  ? "border-amber-200 bg-amber-50"
                  : "border-sky-200 bg-sky-50"
              }`}
            >
              <p
                className={`text-sm font-semibold ${
                  workspaceConfig.dataMode === "live" ? "text-amber-950" : "text-sky-900"
                }`}
              >
                {workspaceConfig.operatorNoticeTitle}
              </p>
              <p
                className={`mt-1 text-sm ${
                  workspaceConfig.dataMode === "live" ? "text-amber-900" : "text-sky-800"
                }`}
              >
                {workspaceConfig.operatorNotice}
              </p>
            </div>
          </div>
        </SectionCard>
        <LoginForm
          defaultEmail={workspaceConfig.loginDefaults.email}
          defaultPassword={workspaceConfig.loginDefaults.password}
          helpText={workspaceConfig.loginHelpText}
          workspaceLabel={workspaceConfig.workspaceLabel}
          workspaceMode={workspaceConfig.dataMode}
        />
      </div>
    </main>
  );
}
