import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { LoginForm } from "@/components/features/auth/login-form";
import { SectionCard } from "@/components/ui/section-card";
import { ACCESS_TOKEN_COOKIE_NAME } from "@/lib/api/access-token";

export default async function LoginPage() {
  const cookieStore = await cookies();
  if (cookieStore.get(ACCESS_TOKEN_COOKIE_NAME)?.value) {
    redirect("/dashboard");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl items-center px-4 py-10 lg:px-6">
      <div className="grid w-full gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <SectionCard
          description="Quotes4 keeps quotes, forecasting, imports, and operational history in one shared business system."
          title="Post production quoting and forecasting"
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
            <div className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-4">
              <p className="text-sm font-semibold text-sky-900">
                Operator notes
              </p>
              <p className="mt-1 text-sm text-sky-800">
                Demo data includes seeded quotes, imports, forecasts, and
                benchmark summaries so the full operational workflow can be
                reviewed end to end.
              </p>
            </div>
          </div>
        </SectionCard>
        <LoginForm />
      </div>
    </main>
  );
}
