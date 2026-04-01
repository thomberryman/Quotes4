export type WorkspaceDataMode = "demo" | "live";

function readPublicValue(value: string | undefined, fallback: string): string {
  const normalized = value?.trim();
  return normalized ? normalized : fallback;
}

function resolveDataMode(): WorkspaceDataMode {
  return process.env.NEXT_PUBLIC_DATA_MODE?.trim().toLowerCase() === "live" ? "live" : "demo";
}

const dataMode = resolveDataMode();

export const workspaceConfig = {
  dataMode,
  appDisplayName: readPublicValue(
    process.env.NEXT_PUBLIC_APP_DISPLAY_NAME,
    dataMode === "live" ? "Quotes4 Live" : "Quotes4 Demo",
  ),
  workspaceLabel: readPublicValue(
    process.env.NEXT_PUBLIC_WORKSPACE_LABEL,
    dataMode === "live" ? "Live Import Workspace" : "Demo Workspace",
  ),
  workspaceDescription: readPublicValue(
    process.env.NEXT_PUBLIC_WORKSPACE_DESCRIPTION,
    dataMode === "live"
      ? "Use this workspace for operational projects, real quote intake, and live actuals imports."
      : "Seeded quotes, forecasts, imports, and benchmark records are available for walkthroughs and workflow testing.",
  ),
  productDescription:
    "Operational quoting, forecasting, quote review, and actuals analysis for post production.",
  operatorNoticeTitle: dataMode === "live" ? "Live data notice" : "Demo data notice",
  operatorNotice:
    dataMode === "live"
      ? "This workspace writes to the live-import database. Only load client, quote, and import data that should remain in the operational record."
      : "Demo data includes seeded quotes, imports, forecasts, and benchmark summaries so the full operational workflow can be reviewed end to end.",
  loginDefaults:
    dataMode === "live"
      ? {
          email: "",
          password: "",
        }
      : {
          email: "admin@quotes4.dev",
          password: "quotes4-admin-password",
        },
  loginHelpText:
    dataMode === "live"
      ? "Use the admin account seeded for this workspace or an invited user account."
      : "The local demo account uses admin@quotes4.dev with password quotes4-admin-password.",
} as const;
