import type { TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/classnames";

interface TextAreaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
}

export function TextAreaField({
  label,
  className,
  ...props
}: TextAreaFieldProps) {
  return (
    <label className="grid gap-1.5">
      {label ? <span className="text-sm font-medium text-slate-700">{label}</span> : null}
      <textarea
        className={cn(
          "min-h-24 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200",
          className
        )}
        {...props}
      />
    </label>
  );
}
