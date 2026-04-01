import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

import { cn } from "@/lib/classnames";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, PropsWithChildren {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  fullWidth?: boolean;
}

const variants: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary:
    "bg-slate-900 text-white hover:bg-slate-700 border border-slate-900",
  secondary:
    "bg-white text-slate-900 hover:bg-slate-50 border border-slate-200",
  ghost:
    "bg-transparent text-slate-700 hover:bg-slate-100 border border-transparent",
  danger:
    "bg-red-700 text-white hover:bg-red-600 border border-red-700"
};

export function Button({
  children,
  className,
  fullWidth = false,
  variant = "secondary",
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-md px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-60",
        variants[variant],
        fullWidth && "w-full",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}
