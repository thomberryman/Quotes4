import type { ReactNode } from "react";

export function SummaryStat({
  label,
  value,
  hint,
  tone
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "positive" | "warning";
}) {
  const valueClass =
    tone === "positive"
      ? "text-emerald-700"
      : tone === "warning"
        ? "text-amber-700"
        : "text-slate-900";

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${valueClass}`}>{value}</p>
      {hint ? <p className="mt-2 text-sm text-slate-600">{hint}</p> : null}
    </article>
  );
}
