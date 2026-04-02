import { ForecastEditor } from "@/components/features/forecasts/forecast-editor";
import { ProjectWorkspaceNav } from "@/components/features/projects/project-workspace-nav";
import { SectionCard } from "@/components/ui/section-card";
import { SummaryStat } from "@/components/ui/summary-stat";
import { PageHeader } from "@/components/layout/page-header";
import { getForecastPolicy, getProjectForecast } from "@/lib/api/forecasts";
import { getProject, getProjectPredictiveGuidance } from "@/lib/api/projects";
import { formatCurrency, formatStatusLabel } from "@/lib/format";
import { getExpectedScenarioSpend } from "@/lib/predictions/advisory-spend";

export default async function ForecastPage({
  params
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const [project, forecast, policy, predictiveGuidance] = await Promise.all([
    getProject(projectId),
    getProjectForecast(projectId),
    getForecastPolicy(),
    getProjectPredictiveGuidance(projectId, { limit: 10 }),
  ]);
  const advisorySpend = getExpectedScenarioSpend(predictiveGuidance);

  return (
    <>
      <PageHeader
        meta={{
          title: "Forecast Editor",
          description: `Edit forecast versions, probabilities, and allocations for ${project.name}.`,
          breadcrumbs: [
            { href: "/projects", label: "Projects" },
            { label: project.name }
          ]
        }}
      />
      <ProjectWorkspaceNav activePath={`/projects/${projectId}/forecast`} projectId={projectId} />
      <SectionCard
        title="Advisory Predicted Spend"
        description="Predicted spend is displayed for context only. Forecast revenue totals and monthly allocations are unchanged."
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <SummaryStat
            label="Predicted spend total"
            value={
              advisorySpend?.predictedTotalCost != null
                ? formatCurrency(
                    advisorySpend.predictedTotalCost,
                    predictiveGuidance.target.quoteCurrencyCode,
                  )
                : "Not available"
            }
          />
          <SummaryStat
            label="Predicted remaining spend"
            value={
              advisorySpend?.predictedRemainingCost != null
                ? formatCurrency(
                    advisorySpend.predictedRemainingCost,
                    predictiveGuidance.target.quoteCurrencyCode,
                  )
                : "Not available"
            }
          />
          <SummaryStat
            label="Confidence / fallback"
            value={advisorySpend ? formatStatusLabel(advisorySpend.confidence) : "Not available"}
            hint={advisorySpend ? formatStatusLabel(advisorySpend.fallbackTier) : "No spend scenario output"}
          />
          <SummaryStat
            label="Top comparables"
            value={predictiveGuidance.topComparables?.length ?? 0}
            hint="Used by advisory prediction"
          />
        </div>
      </SectionCard>
      <ForecastEditor
        initialForecast={forecast}
        initialPolicy={policy}
        projectId={projectId}
        projectScheduleRanges={project.scheduleRanges}
      />
    </>
  );
}
