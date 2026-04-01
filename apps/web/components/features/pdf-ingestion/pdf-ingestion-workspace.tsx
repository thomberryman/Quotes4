"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiClientError } from "@quotes4/contracts";
import type { ProjectSummary, QuoteIngestionRunSummary } from "@quotes4/contracts";
import { useMemo, useState } from "react";

import { getBrowserApiClient } from "@/lib/api/browser-client";
import { validateQuotePdfFile } from "@/lib/forms/validation";
import { formatDateTime, formatStatusLabel } from "@/lib/format";
import { queryKeys } from "@/lib/query/keys";

import { SelectField } from "@/components/forms/select-field";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SummaryStat } from "@/components/ui/summary-stat";

function toBase64(bytes: Uint8Array) {
  let binary = "";
  bytes.forEach((value) => {
    binary += String.fromCharCode(value);
  });
  return btoa(binary);
}

async function buildChecksum(file: File) {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return toBase64(new Uint8Array(digest));
}

export function PdfIngestionWorkspace({
  initialRuns,
  projects,
}: {
  initialRuns: QuoteIngestionRunSummary[];
  projects: ProjectSummary[];
}) {
  const api = getBrowserApiClient();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [projectId, setProjectId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const runsQuery = useQuery({
    initialData: { items: initialRuns },
    queryFn: async () => api.listQuoteIngestionRuns(),
    queryKey: queryKeys.quoteIngestionRuns,
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => item.status === "queued") ? 5000 : false,
  });

  const counts = useMemo(() => {
    const items = runsQuery.data?.items ?? [];
    return {
      queued: items.filter((item) => item.status === "queued").length,
      inReview: items.filter((item) => item.status === "in_review").length,
      approved: items.filter((item) => item.status === "approved").length,
    };
  }, [runsQuery.data]);

  const uploadMutation = useMutation({
    mutationFn: async () => {
      const file = selectedFile;
      const validationError = validateQuotePdfFile(file);
      if (validationError) {
        throw new Error(validationError);
      }
      if (!file) {
        throw new Error("Choose a PDF file before uploading.");
      }
      const checksumSha256 = await buildChecksum(file);
      const uploadIntent = await api.createQuoteIngestionUploadIntent({
        fileName: file.name,
        contentType: file.type || "application/pdf",
        sizeBytes: file.size,
        checksumSha256,
      });

      const uploadResponse = await fetch(uploadIntent.uploadUrl, {
        method: "PUT",
        headers: uploadIntent.requiredHeaders,
        body: file,
      });
      if (!uploadResponse.ok) {
        throw new Error("The file upload to object storage failed.");
      }

      const finalized = await api.finalizeQuoteIngestionUpload({
        fileId: uploadIntent.file.fileId,
        objectKey: uploadIntent.file.objectKey,
        checksumSha256,
      });

      return api.createQuoteIngestionRun({
        uploadedFileId: finalized.file.fileId,
        projectId: projectId || null,
      });
    },
    onSuccess: async (run) => {
      setError(null);
      setSelectedFile(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.quoteIngestionRuns });
      router.push(`/imports/pdf-ingestion/${run.id}`);
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError || caughtError instanceof Error
          ? caughtError.message
          : "Could not upload the PDF and start ingestion.",
      );
    },
  });

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <SummaryStat
          label="Queued Runs"
          value={counts.queued}
          hint="Awaiting parser output from the worker."
          tone={counts.queued > 0 ? "warning" : "default"}
        />
        <SummaryStat
          label="In Review"
          value={counts.inReview}
          hint="Human review required before quote creation."
          tone={counts.inReview > 0 ? "warning" : "default"}
        />
        <SummaryStat
          label="Approved"
          value={counts.approved}
          hint="Runs already converted into quote versions."
          tone={counts.approved > 0 ? "positive" : "default"}
        />
      </div>

      <SectionCard
        title="Upload Quote PDF"
        description="Upload a quote PDF into staging. The parser output stays in review until a user approves or corrects it."
        actions={
          <Button
            disabled={Boolean(uploadMutation.isPending || validateQuotePdfFile(selectedFile))}
            onClick={() => uploadMutation.mutate()}
            variant="primary"
          >
            {uploadMutation.isPending ? "Uploading..." : "Upload And Start Review"}
          </Button>
        }
      >
        <div className="grid gap-4 lg:grid-cols-[1.4fr_0.8fr]">
          <label className="grid gap-1.5">
            <span className="text-sm font-medium text-slate-700">Source PDF</span>
            <input
              accept="application/pdf"
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
              onChange={(event) => {
                const nextFile = event.target.files?.[0] ?? null;
                setSelectedFile(nextFile);
                setError(validateQuotePdfFile(nextFile));
              }}
              type="file"
            />
            <span className="text-xs text-slate-500">
              PDFs are uploaded to file storage first, then queued for extraction review.
            </span>
          </label>
          <SelectField
            label="Project Hint"
            onChange={(event) => setProjectId(event.target.value)}
            value={projectId}
          >
            <option value="">Auto-match after extraction</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </SelectField>
        </div>
        {selectedFile ? (
          <p className="mt-4 text-sm text-slate-600">
            Selected file: <span className="font-medium text-slate-900">{selectedFile.name}</span>
          </p>
        ) : null}
        {error ? (
          <div className="mt-4">
            <ErrorState title="Upload failed" description={error} />
          </div>
        ) : null}
      </SectionCard>

      <SectionCard
        title="Recent Runs"
        description="Each run remains staged until review is complete. Open a run to inspect extraction confidence, correct fields, and approve the quote version."
      >
        {runsQuery.isError ? (
          <ErrorState
            title="Could not load ingestion runs"
            description="The backend did not return the current ingestion run list."
          />
        ) : runsQuery.data?.items.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="py-2 pr-4 font-medium">File</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                  <th className="py-2 pr-4 font-medium">Target</th>
                  <th className="py-2 pr-4 font-medium">Updated</th>
                  <th className="py-2 font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {runsQuery.data.items.map((run) => (
                  <tr key={run.id}>
                    <td className="py-3 pr-4">
                      <div className="font-medium text-slate-900">{run.fileName ?? run.id}</div>
                      <div className="text-xs text-slate-500">{run.id}</div>
                    </td>
                    <td className="py-3 pr-4">
                      <StatusBadge value={run.status} />
                    </td>
                    <td className="py-3 pr-4 text-slate-600">
                      {run.selectedTargetMode
                        ? formatStatusLabel(run.selectedTargetMode)
                        : "Unassigned"}
                    </td>
                    <td className="py-3 pr-4 text-slate-600">
                      {formatDateTime(run.updatedAt)}
                    </td>
                    <td className="py-3">
                      <Link
                        className="font-medium text-slate-900 underline"
                        href={`/imports/pdf-ingestion/${run.id}`}
                      >
                        Open Review
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No PDF ingestion runs yet"
            description="Upload a quote PDF to create the first staged review run."
          />
        )}
      </SectionCard>
    </div>
  );
}
