import { PageHeader } from "@/components/layout/page-header";
import { ProjectWorkspaceNav } from "@/components/features/projects/project-workspace-nav";
import { QuoteBuilderWorkspace } from "@/components/features/quotes/quote-builder-workspace";
import { getProject, getProjectPredictiveGuidance } from "@/lib/api/projects";
import { listQuotes } from "@/lib/api/quotes";

export default async function QuoteBuilderPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const [project, quotes] = await Promise.all([
    getProject(projectId),
    listQuotes(projectId),
  ]);
  const initialSelectedVersionId = quotes.items[0]?.currentVersionId ?? null;
  const initialPredictiveGuidance = initialSelectedVersionId
    ? await getProjectPredictiveGuidance(projectId, {
        quoteVersionId: initialSelectedVersionId,
        limit: 10,
      })
    : null;

  return (
    <>
      <PageHeader
        meta={{
          title: "Quote Builder",
          description: `Build and manage quote versions for ${project.name}.`,
          breadcrumbs: [
            { href: "/projects", label: "Projects" },
            { label: project.name },
          ],
        }}
      />
      <ProjectWorkspaceNav
        activePath={`/projects/${projectId}/quotes/builder`}
        projectId={projectId}
      />
      <QuoteBuilderWorkspace
        projectId={projectId}
        projectName={project.name}
        quotes={quotes.items}
        initialSelectedVersionId={initialSelectedVersionId}
        initialPredictiveGuidance={initialPredictiveGuidance}
      />
    </>
  );
}
