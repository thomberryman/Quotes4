import { ProjectScenarioWorkspace } from "@/components/features/predictions/project-scenario-workspace";
import { ProjectWorkspaceNav } from "@/components/features/projects/project-workspace-nav";
import { PageHeader } from "@/components/layout/page-header";
import { getProject, getProjectPredictiveGuidance, listPredictionRuns } from "@/lib/api/projects";

export default async function ScenarioPlanningPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const [project, predictiveGuidance] = await Promise.all([
    getProject(projectId),
    getProjectPredictiveGuidance(projectId, { limit: 25 }),
  ]);
  const runList = await listPredictionRuns(projectId);

  return (
    <>
      <PageHeader
        meta={{
          title: "Scenario Planning",
          description: `Adjust explainable prediction scenarios and promote them into forecast drafts for ${project.name}.`,
          breadcrumbs: [
            { href: "/projects", label: "Projects" },
            { label: project.name },
          ],
        }}
      />
      <ProjectWorkspaceNav
        activePath={`/projects/${projectId}/scenarios`}
        projectId={projectId}
      />
      <ProjectScenarioWorkspace
        initialProject={project}
        initialRun={predictiveGuidance}
        initialRunList={runList.items}
        projectId={projectId}
      />
    </>
  );
}
