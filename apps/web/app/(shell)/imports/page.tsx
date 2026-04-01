import Link from "next/link";

import { PageHeader } from "@/components/layout/page-header";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";

export default function ImportsPage() {
  return (
    <>
      <PageHeader
        meta={{
          title: "Imports",
          description:
            "Central entry point for staged external data. PDF and CETA workflows both preserve source files, staged review data, and approval lineage."
        }}
      />
      <div className="grid gap-6 xl:grid-cols-2">
        <SectionCard title="PDF Ingestion Review" description="Upload quote PDFs into staging, review the extraction output, and approve the reviewed result into quote records.">
          <div className="space-y-4">
            <StatusBadge value="active" />
            <p className="text-sm text-slate-600">
              The PDF ingestion workflow is live. Uploads go through file storage, parser output
              stays staged for human review, and approvals create auditable quote versions.
            </p>
            <Link className="text-sm font-medium text-slate-900 underline" href="/imports/pdf-ingestion">
              Open PDF ingestion workspace
            </Link>
          </div>
        </SectionCard>
        <SectionCard title="CETA Import Review" description="Review staged CETA data and approval outcomes before posting actuals.">
          <div className="space-y-4">
            <StatusBadge value="active" />
            <p className="text-sm text-slate-600">
              CETA imports are live. Raw exports stay immutable, staged rows keep their source
              payload, and approvals post mapped actuals with repeat and variance review.
            </p>
            <Link className="text-sm font-medium text-slate-900 underline" href="/imports/ceta">
              Open CETA review screen
            </Link>
          </div>
        </SectionCard>
      </div>
    </>
  );
}
