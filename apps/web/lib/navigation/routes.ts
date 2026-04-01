import type { NavGroup } from "./types";

export const navigationGroups: NavGroup[] = [
  {
    label: "Home",
    items: [
      {
        label: "Dashboard",
        href: "/dashboard",
        description: "Operational overview, queue state, and quick links.",
      },
    ],
  },
  {
    label: "Directory",
    items: [
      {
        label: "Clients",
        href: "/clients",
        description: "Counterparty directory and default commercial details.",
      },
      {
        label: "Contacts",
        href: "/contacts",
        description: "People directory used across clients and projects.",
      },
    ],
  },
  {
    label: "Operations",
    items: [
      {
        label: "Projects",
        href: "/projects",
        description:
          "Project list with drill-down into quote, forecast, and comparables.",
      },
      {
        label: "Imports",
        href: "/imports",
        description: "PDF and CETA ingestion workflows.",
      },
    ],
  },
];

export const projectWorkspaceLinks = [
  {
    label: "Quote Builder",
    href: "quotes/builder",
  },
  {
    label: "Quote Compare",
    href: "quotes/compare",
  },
  {
    label: "Forecast",
    href: "forecast",
  },
  {
    label: "Comparables",
    href: "comparables",
  },
  {
    label: "Scenarios",
    href: "scenarios",
  },
  {
    label: "Quote vs Actual",
    href: "actuals-vs-quote",
  },
] as const;
