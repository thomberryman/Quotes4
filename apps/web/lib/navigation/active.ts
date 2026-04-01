import type { NavGroup } from "./types";

export function isNavItemActive(pathname: string, href: string): boolean {
  if (href === "/dashboard") {
    return pathname === href;
  }

  return pathname === href || pathname.startsWith(`${href}/`);
}

export function flattenNav(groups: NavGroup[]) {
  return groups.flatMap((group) => group.items);
}
