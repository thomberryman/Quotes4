import type { PropsWithChildren, ReactNode } from "react";

import { cn } from "@/lib/classnames";

export function SectionCard({
  title,
  description,
  actions,
  children,
  className
}: PropsWithChildren<{
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}>) {
  return (
    <section
      className={cn(
        "rounded-xl border border-slate-200 bg-white shadow-sm",
        className
      )}
    >
      <header className="flex flex-col gap-3 border-b border-slate-200 px-5 py-4 md:flex-row md:items-start md:justify-between">
        <div className="space-y-1">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          {description ? (
            <p className="max-w-3xl text-sm text-slate-600">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
      </header>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}
