import { notFound } from "next/navigation";

import { CetaBatchReviewWorkspace } from "@/components/features/imports/ceta-batch-review-workspace";
import { PageHeader } from "@/components/layout/page-header";
import {
  getActualsImportBatch,
  listActualsImportRows,
} from "@/lib/api/actuals-imports";
import { listDisciplines } from "@/lib/api/directories";
import { listProjects } from "@/lib/api/projects";

export default async function CetaBatchReviewPage({
  params,
}: {
  params: Promise<{ batchId: string }>;
}) {
  const { batchId } = await params;

  const [batch, rows, projects, disciplines] = await Promise.all([
    getActualsImportBatch(batchId).catch(() => null),
    listActualsImportRows(batchId).catch(() => null),
    listProjects(),
    listDisciplines(),
  ]);

  if (!batch || !rows) {
    notFound();
  }

  return (
    <>
      <PageHeader
        meta={{
          title: "CETA Batch Review",
          description:
            "Review staged CETA rows, correct mappings, resolve repeats, and approve reconciled actuals into the operational ledger."
        }}
      />
      <CetaBatchReviewWorkspace
        batchId={batchId}
        initialBatch={batch}
        initialRows={rows}
        initialProjects={projects}
        initialDisciplines={disciplines}
      />
    </>
  );
}
