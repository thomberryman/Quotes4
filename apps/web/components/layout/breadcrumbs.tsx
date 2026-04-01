import Link from "next/link";

export function Breadcrumbs({
  items
}: {
  items: { label: string; href?: string }[];
}) {
  return (
    <nav className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
      {items.map((item, index) => (
        <div className="flex items-center gap-2" key={`${item.label}-${index}`}>
          {index > 0 ? <span>/</span> : null}
          {item.href ? (
            <Link className="hover:text-slate-900" href={item.href}>
              {item.label}
            </Link>
          ) : (
            <span className="text-slate-900">{item.label}</span>
          )}
        </div>
      ))}
    </nav>
  );
}
