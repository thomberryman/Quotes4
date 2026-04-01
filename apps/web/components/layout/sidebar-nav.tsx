"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/classnames";
import { isNavItemActive } from "@/lib/navigation/active";
import type { NavGroup } from "@/lib/navigation/types";

export function SidebarNav({
  groups,
  onNavigate,
}: {
  groups: NavGroup[];
  onNavigate?: () => void;
}) {
  const pathname = usePathname();

  return (
    <nav className="space-y-6">
      {groups.map((group) => (
        <div className="space-y-2" key={group.label}>
          <p className="px-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            {group.label}
          </p>
          <div className="space-y-1">
            {group.items.map((item) => {
              const active = isNavItemActive(pathname, item.href);
              return (
                <Link
                  className={cn(
                    "block rounded-lg border px-3 py-3 transition",
                    active
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-transparent bg-white text-slate-700 hover:border-slate-200 hover:bg-slate-50",
                  )}
                  href={item.href}
                  key={item.href}
                  {...(onNavigate ? { onClick: onNavigate } : {})}
                >
                  <p
                    className={cn(
                      "text-sm font-medium",
                      active && "text-white",
                    )}
                  >
                    {item.label}
                  </p>
                  <p
                    className={cn(
                      "mt-1 text-xs leading-5",
                      active ? "text-slate-300" : "text-slate-500",
                    )}
                  >
                    {item.description}
                  </p>
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}
