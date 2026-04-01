import { PageHeader } from "@/components/layout/page-header";
import { OperationalDashboardPage } from "@/features/dashboard/operational-dashboard-page";

export default function DashboardPage() {
  return (
    <>
      <PageHeader
        meta={{
          title: "Dashboard",
          description:
            "Operational view of pipeline, forecast, client history, benchmark coverage, and explainable comparable ranges.",
        }}
      />
      <OperationalDashboardPage />
    </>
  );
}
