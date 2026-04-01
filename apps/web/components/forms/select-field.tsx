import type { PropsWithChildren, SelectHTMLAttributes } from "react";

import { cn } from "@/lib/classnames";

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement>, PropsWithChildren {
  label?: string;
}

export function SelectField({
  label,
  className,
  children,
  ...props
}: SelectFieldProps) {
  return (
    <label className="grid gap-1.5">
      {label ? <span className="text-sm font-medium text-slate-700">{label}</span> : null}
      <select
        className={cn(
          "rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200",
          className
        )}
        {...props}
      >
        {children}
      </select>
    </label>
  );
}
