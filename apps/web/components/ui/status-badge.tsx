import { cn } from "@/lib/classnames";
import { formatStatusLabel } from "@/lib/format";

const toneMap: Record<string, string> = {
  draft: "bg-amber-50 text-amber-800 ring-amber-200",
  issued: "bg-sky-50 text-sky-800 ring-sky-200",
  queued: "bg-amber-50 text-amber-800 ring-amber-200",
  running: "bg-sky-50 text-sky-800 ring-sky-200",
  succeeded: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  failed: "bg-rose-50 text-rose-800 ring-rose-200",
  approved: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  active: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  awarded: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  info: "bg-sky-50 text-sky-800 ring-sky-200",
  warning: "bg-amber-50 text-amber-800 ring-amber-200",
  low: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  medium: "bg-amber-50 text-amber-800 ring-amber-200",
  high: "bg-rose-50 text-rose-800 ring-rose-200",
  pending: "bg-amber-50 text-amber-800 ring-amber-200",
  blocked: "bg-rose-50 text-rose-800 ring-rose-200",
  bid: "bg-slate-100 text-slate-700 ring-slate-200",
  complete: "bg-slate-100 text-slate-700 ring-slate-200",
  archived: "bg-slate-100 text-slate-700 ring-slate-200"
};

export function StatusBadge({
  value,
  className
}: {
  value: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset",
        toneMap[value] ?? "bg-slate-100 text-slate-700 ring-slate-200",
        className
      )}
    >
      {formatStatusLabel(value)}
    </span>
  );
}
