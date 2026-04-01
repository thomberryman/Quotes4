import { ForecastEditor } from "@/components/features/forecasts/forecast-editor";
import { ProjectWorkspaceNav } from "@/components/features/projects/project-workspace-nav";
import { PageHeader } from "@/components/layout/page-header";
import { getForecastPolicy, getProjectForecast } from "@/lib/api/forecasts";
import { getProject } from "@/lib/api/projects";

export default async function ForecastPage({
  params
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const [project, forecast, policy] = await Promise.all([
    getProject(projectId),
    getProjectForecast(projectId),
    getForecastPolicy()
  ]);

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
      <ForecastEditor
        initialForecast={forecast}
        initialPolicy={policy}
        projectId={projectId}
        projectScheduleRanges={project.scheduleRanges}
      />
    </>
  );
}
