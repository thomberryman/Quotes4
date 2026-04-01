import { PageHeader } from "@/components/layout/page-header";
import { CetaImportsWorkspace } from "@/components/features/imports/ceta-imports-workspace";
import { listActualsImportBatches } from "@/lib/api/actuals-imports";
import { listProjects } from "@/lib/api/projects";

export default async function CetaReviewPage() {
  const [batches, projects] = await Promise.all([
    listActualsImportBatches(),
    listProjects(),
  ]);

  return (
    <>
      <PageHeader
        meta={{
          title: "CETA Import Review",
          description:
            "Upload CETA exports into immutable staging, review row mapping decisions, and approve reconciled actuals."
        }}
      />
      <CetaImportsWorkspace
        initialBatches={batches}
        initialProjects={projects}
      />
    </>
  );
}
