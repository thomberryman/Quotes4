import { PageHeader } from "@/components/layout/page-header";
import { ProjectWorkspaceNav } from "@/components/features/projects/project-workspace-nav";
import { QuoteVersionComparison } from "@/components/features/quotes/quote-version-comparison";
import { getProject } from "@/lib/api/projects";
import { listQuotes } from "@/lib/api/quotes";

export default async function QuoteComparePage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const [project, quotes] = await Promise.all([
    getProject(projectId),
    listQuotes(projectId),
  ]);

  return (
    <>
      <PageHeader
        meta={{
          title: "Quote Version Comparison",
          description: `Compare quote versions side by side for ${project.name}.`,
          breadcrumbs: [
            { href: "/projects", label: "Projects" },
            { label: project.name },
          ],
        }}
      />
      <ProjectWorkspaceNav
        activePath={`/projects/${projectId}/quotes/compare`}
        projectId={projectId}
      />
      <QuoteVersionComparison quotes={quotes.items} />
    </>
  );
}
