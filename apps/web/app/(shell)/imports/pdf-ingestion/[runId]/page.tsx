import { notFound } from "next/navigation";

import { PdfIngestionRunWorkspace } from "@/components/features/pdf-ingestion/pdf-ingestion-run-workspace";
import { PageHeader } from "@/components/layout/page-header";
import { listProjects } from "@/lib/api/projects";
import { getQuoteIngestionRun } from "@/lib/api/quote-ingestion";
import { listQuotes } from "@/lib/api/quotes";

export default async function PdfIngestionRunPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;

  const [run, projects, quotes] = await Promise.all([
    getQuoteIngestionRun(runId).catch(() => null),
    listProjects(),
    listQuotes(),
  ]);

  if (!run) {
    notFound();
  }

  return (
    <>
      <PageHeader
        meta={{
          title: "PDF Ingestion Run",
          description:
            "Review the staged extraction output, correct fields and line items, and approve the reviewed quote into operational records."
        }}
      />
      <PdfIngestionRunWorkspace
        initialRun={run}
        projects={projects.items}
        quotes={quotes.items}
      />
    </>
  );
}
