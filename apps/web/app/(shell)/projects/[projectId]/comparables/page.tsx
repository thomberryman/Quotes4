import { ComparablesWorkspace } from "@/components/features/comparables/comparables-workspace";
import { ProjectWorkspaceNav } from "@/components/features/projects/project-workspace-nav";
import { PageHeader } from "@/components/layout/page-header";
import { getProjectComparables, getProjectRecommendations } from "@/lib/api/comparables";
import { getProject, getProjectPredictiveGuidance } from "@/lib/api/projects";

export default async function ComparablesPage({
  params
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const [project, comparables, recommendations, predictiveGuidance] = await Promise.all([
    getProject(projectId),
    getProjectComparables(projectId, { includePinned: true, limit: 25 }),
    getProjectRecommendations(projectId, { limit: 25 }),
    getProjectPredictiveGuidance(projectId, { limit: 25 })
  ]);

  return (
    <>
      <PageHeader
        meta={{
          title: "Comparable Projects",
          description: `Review explainable comparable-project signals and recommended ranges for ${project.name}.`,
          breadcrumbs: [
            { href: "/projects", label: "Projects" },
            { label: project.name }
          ]
        }}
      />
      <ProjectWorkspaceNav
        activePath={`/projects/${projectId}/comparables`}
        projectId={projectId}
      />
      <ComparablesWorkspace
        initialComparables={comparables}
        initialPredictiveGuidance={predictiveGuidance}
        initialRecommendations={recommendations}
        projectId={projectId}
        projectDisciplines={project.disciplines.map((discipline) => ({
          code: discipline.disciplineCode,
          name: discipline.disciplineName
        }))}
      />
    </>
  );
}
