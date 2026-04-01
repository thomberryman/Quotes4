import Link from "next/link";

import { cn } from "@/lib/classnames";
import type { RouteMeta } from "@/lib/navigation/types";

import { Breadcrumbs } from "./breadcrumbs";

export function PageHeader({ meta }: { meta: RouteMeta }) {
  return (
    <header className="space-y-4">
      {meta.breadcrumbs?.length ? <Breadcrumbs items={meta.breadcrumbs} /> : null}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold text-slate-950">{meta.title}</h1>
          <p className="max-w-3xl text-sm text-slate-600">{meta.description}</p>
        </div>
        {meta.actions?.length ? (
          <div className="flex flex-wrap gap-2">
            {meta.actions.map((action) =>
              action.href ? (
                <Link
                  className={cn(
                    "inline-flex items-center justify-center rounded-md border px-3 py-2 text-sm font-medium transition",
                    action.variant === "primary"
                      ? "border-slate-900 bg-slate-900 text-white hover:bg-slate-700"
                      : "border-slate-200 bg-white text-slate-900 hover:bg-slate-50"
                  )}
                  href={action.href}
                  key={action.label}
                >
                  {action.label}
                </Link>
              ) : null
            )}
          </div>
        ) : null}
      </div>
    </header>
  );
}
