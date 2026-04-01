import { cn } from "@/lib/classnames";

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  disabled = false
}: {
  options: { label: string; value: T }[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
}) {
  return (
    <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-1">
      {options.map((option) => (
        <button
          key={option.value}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-60",
            option.value === value
              ? "bg-white text-slate-900 shadow-sm"
              : "text-slate-600 hover:text-slate-900"
          )}
          disabled={disabled}
          onClick={() => onChange(option.value)}
          type="button"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
