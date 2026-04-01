"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type {
  ActualsImportBatchListResponse,
  CetaImportCoverageMode,
  ProjectListResponse,
} from "@quotes4/contracts";
import { ApiClientError } from "@quotes4/contracts";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { TextInput } from "@/components/forms/text-input";
import { SelectField } from "@/components/forms/select-field";
import { getBrowserApiClient } from "@/lib/api/browser-client";
import { validateCetaExportFile } from "@/lib/forms/validation";
import { formatDateTime } from "@/lib/format";
import { queryKeys } from "@/lib/query/keys";

async function sha256Base64(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  const bytes = new Uint8Array(digest);
  let binary = "";
  bytes.forEach((value) => {
    binary += String.fromCharCode(value);
  });
  return btoa(binary);
}

export function CetaImportsWorkspace({
  initialBatches,
  initialProjects,
}: {
  initialBatches: ActualsImportBatchListResponse;
  initialProjects: ProjectListResponse;
}) {
  const api = getBrowserApiClient();
  const queryClient = useQueryClient();
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [coverageMode, setCoverageMode] =
    useState<CetaImportCoverageMode>("snapshot");
  const [projectId, setProjectId] = useState("");
  const [sourceExportId, setSourceExportId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const batchesQuery = useQuery({
    initialData: initialBatches,
    queryFn: async () => api.listActualsImportBatches(),
    queryKey: queryKeys.actualsImportBatches,
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      const selectedFile = file;
      const validationError = validateCetaExportFile(selectedFile);
      if (validationError) {
        throw new Error(validationError);
      }
      if (!selectedFile) {
        throw new Error("Choose a CETA export first.");
      }
      const checksumSha256 = await sha256Base64(selectedFile);
      const uploadIntent = await api.createUploadIntent({
        fileName: selectedFile.name,
        contentType: selectedFile.type || "text/csv",
        sizeBytes: selectedFile.size,
        checksumSha256,
        fileCategory: "ceta_export",
      });

      const response = await fetch(uploadIntent.uploadUrl, {
        body: selectedFile,
        headers: uploadIntent.requiredHeaders,
        method: "PUT",
      });
      if (!response.ok) {
        throw new Error("File upload failed before batch creation.");
      }

      await api.finalizeUpload({
        fileId: uploadIntent.fileId,
        objectKey: uploadIntent.objectKey,
        checksumSha256,
      });

      return api.createActualsImportBatch({
        uploadedFileId: uploadIntent.fileId,
        coverageMode,
        projectId: projectId || null,
        sourceSystem: "ceta",
        sourceExportId: sourceExportId || null,
      });
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError || caughtError instanceof Error
          ? caughtError.message
          : "Could not create the CETA import batch.",
      );
    },
    onSuccess: async (batch) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.actualsImportBatches });
      router.push(`/imports/ceta/${batch.id}`);
    },
  });

  return (
    <div className="space-y-6">
      {error ? <ErrorState title="Import setup failed" description={error} /> : null}

      <SectionCard
        title="New CETA Batch"
        description="Upload a finalized CETA export, register a batch, then open the review workspace to parse and reconcile the staged rows."
        actions={
          <Button
            disabled={Boolean(uploadMutation.isPending || validateCetaExportFile(file))}
            onClick={() => uploadMutation.mutate()}
            type="button"
            variant="primary"
          >
            {uploadMutation.isPending ? "Creating..." : "Create batch"}
          </Button>
        }
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <label className="grid gap-1.5">
            <span className="text-sm font-medium text-slate-700">CETA export</span>
            <input
              accept=".csv,.xlsx,.xls"
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
              onChange={(event) => {
                const nextFile = event.target.files?.[0] ?? null;
                setFile(nextFile);
                setError(validateCetaExportFile(nextFile));
              }}
              type="file"
            />
          </label>
          <SelectField
            label="Coverage mode"
            onChange={(event) =>
              setCoverageMode(event.target.value as CetaImportCoverageMode)
            }
            value={coverageMode}
          >
            <option value="snapshot">Snapshot</option>
            <option value="incremental">Incremental</option>
          </SelectField>
          <SelectField
            label="Project scope"
            onChange={(event) => setProjectId(event.target.value)}
            value={projectId}
          >
            <option value="">Unscoped review</option>
            {initialProjects.items.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </SelectField>
          <TextInput
            label="Source export ID"
            onChange={(event) => setSourceExportId(event.target.value)}
            placeholder="Optional source export reference"
            value={sourceExportId}
          />
        </div>
      </SectionCard>

      <SectionCard
        title="Batch History"
        description="Open an existing batch to parse, review row mappings, or approve the staged import."
      >
        {batchesQuery.data.items.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
              <thead>
                <tr className="text-slate-500">
                  <th className="px-3 py-2 font-medium">Batch</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Coverage</th>
                  <th className="px-3 py-2 font-medium">Rows</th>
                  <th className="px-3 py-2 font-medium">Uploaded</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {batchesQuery.data.items.map((batch) => (
                  <tr key={batch.id} className="align-top">
                    <td className="px-3 py-3">
                      <div className="space-y-1">
                        <Link
                          className="font-medium text-slate-900 underline"
                          href={`/imports/ceta/${batch.id}`}
                        >
                          {batch.projectName ?? batch.id}
                        </Link>
                        <p className="text-xs text-slate-500">{batch.id}</p>
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <StatusBadge value={batch.status} />
                    </td>
                    <td className="px-3 py-3 text-slate-700">
                      {batch.coverageMode}
                    </td>
                    <td className="px-3 py-3 text-slate-700">{batch.rowCount}</td>
                    <td className="px-3 py-3 text-slate-700">
                      {formatDateTime(batch.uploadedAt)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No CETA batches yet"
            description="Create the first staged import batch to begin reconciliation."
          />
        )}
      </SectionCard>
    </div>
  );
}
