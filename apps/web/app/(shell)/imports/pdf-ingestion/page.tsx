import { PdfIngestionWorkspace } from "@/components/features/pdf-ingestion/pdf-ingestion-workspace";
import { PageHeader } from "@/components/layout/page-header";
import { listProjects } from "@/lib/api/projects";
import { listQuoteIngestionRuns } from "@/lib/api/quote-ingestion";

export default async function PdfIngestionPage() {
  const [runs, projects] = await Promise.all([
    listQuoteIngestionRuns(),
    listProjects(),
  ]);

  return (
    <>
      <PageHeader
        meta={{
          title: "PDF Ingestion Review",
          description:
            "Upload quote PDFs into staging, review extracted fields and line items, then approve the reviewed result into quote records."
        }}
      />
      <PdfIngestionWorkspace initialRuns={runs.items} projects={projects.items} />
    </>
  );
}
