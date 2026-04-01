import type { ReactNode } from "react";

export interface NavItem {
  label: string;
  href: string;
  description: string;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export interface RouteMeta {
  title: string;
  description: string;
  breadcrumbs?: { label: string; href?: string }[];
  actions?: PageAction[];
}

export interface PageAction {
  label: string;
  href?: string;
  variant?: "primary" | "secondary";
}

export interface TableColumn<T> {
  key: string;
  header: string;
  className?: string;
  render: (row: T) => ReactNode;
}
