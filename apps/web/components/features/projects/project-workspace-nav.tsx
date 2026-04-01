import Link from "next/link";

import { cn } from "@/lib/classnames";
import { projectWorkspaceLinks } from "@/lib/navigation/routes";

export function ProjectWorkspaceNav({
  projectId,
  activePath,
}: {
  projectId: string;
  activePath: string;
}) {
  return (
    <div className="overflow-x-auto">
      <div className="inline-flex min-w-full gap-2 rounded-xl border border-slate-200 bg-white p-2 shadow-sm">
        {projectWorkspaceLinks.map((link) => {
          const href = `/projects/${projectId}/${link.href}`;
          const active = activePath === href;
          return (
            <Link
              className={cn(
                "rounded-lg px-3 py-2 text-sm font-medium transition",
                active
                  ? "bg-slate-900 text-white"
                  : "text-slate-700 hover:bg-slate-100",
              )}
              href={href}
              key={href}
            >
              {link.label}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
