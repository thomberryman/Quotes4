import { ProjectActualsVsQuoteWorkspace } from "@/components/features/projects/project-actuals-vs-quote-workspace";
import { ProjectWorkspaceNav } from "@/components/features/projects/project-workspace-nav";
import { PageHeader } from "@/components/layout/page-header";
import {
  getProjectActualsVsQuote,
  getProjectPredictiveGuidance,
} from "@/lib/api/projects";

export default async function QuoteVsActualPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const [projectActualsVsQuote, predictiveGuidance] = await Promise.all([
    getProjectActualsVsQuote(projectId),
    getProjectPredictiveGuidance(projectId, { limit: 25 }),
  ]);

  return (
    <>
      <PageHeader
        meta={{
          title: "Quote vs Actual Comparison",
          description: `Variance analysis for ${projectActualsVsQuote.projectName}.`,
          breadcrumbs: [
            { href: "/projects", label: "Projects" },
            { label: projectActualsVsQuote.projectName },
          ],
        }}
      />
      <ProjectWorkspaceNav
        activePath={`/projects/${projectId}/actuals-vs-quote`}
        projectId={projectId}
      />
      <ProjectActualsVsQuoteWorkspace
        predictiveGuidance={predictiveGuidance}
        projectActualsVsQuote={projectActualsVsQuote}
      />
    </>
  );
}
