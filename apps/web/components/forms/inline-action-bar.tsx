import type { PropsWithChildren } from "react";

import { cn } from "@/lib/classnames";

export function InlineActionBar({
  children,
  sticky = false
}: PropsWithChildren<{ sticky?: boolean }>) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3",
        sticky && "sticky bottom-4 z-10"
      )}
    >
      {children}
    </div>
  );
}
