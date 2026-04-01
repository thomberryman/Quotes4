"use client";

import Link from "next/link";
import type { FormEvent } from "react";
import { useEffect, useMemo, useState, useTransition } from "react";

import type { ProjectRead, ProjectStatus, ProjectSummary } from "@quotes4/contracts";
import { ApiClientError } from "@quotes4/contracts";

import { DataTable } from "@/components/data-table/data-table";
import { SearchInput } from "@/components/forms/search-input";
import { SelectField } from "@/components/forms/select-field";
import { TableToolbar } from "@/components/data-table/table-toolbar";
import { TextAreaField } from "@/components/forms/text-area-field";
import { TextInput } from "@/components/forms/text-input";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { getBrowserApiClient } from "@/lib/api/browser-client";
import { formatDateTime } from "@/lib/format";
import {
  type ProjectCreateFormValues,
  validateProjectCreateForm
} from "@/lib/forms/validation";
import type { TableColumn } from "@/lib/navigation/types";

const PROJECT_STATUS_OPTIONS: Array<{ label: string; value: ProjectStatus }> = [
  { label: "Bid", value: "bid" },
  { label: "Awarded", value: "awarded" },
  { label: "Lost", value: "lost" },
  { label: "Active", value: "active" },
  { label: "Complete", value: "complete" },
  { label: "Archived", value: "archived" }
];

const columns: TableColumn<ProjectSummary>[] = [
  {
    key: "project",
    header: "Project",
    render: (project) => (
      <div>
        <p className="font-medium text-slate-900">{project.name}</p>
        <p className="text-xs text-slate-500">{project.code ?? "No project code"}</p>
      </div>
    )
  },
  {
    key: "client",
    header: "Primary client",
    render: (project) => project.primaryClientName ?? "Not set"
  },
  {
    key: "currency",
    header: "Quote currency",
    render: (project) => project.quoteCurrencyCode ?? "Not set"
  },
  {
    key: "status",
    header: "Status",
    render: (project) => <StatusBadge value={project.status} />
  },
  {
    key: "updated",
    header: "Updated",
    render: (project) => formatDateTime(project.updatedAt)
  },
  {
    key: "workspaces",
    header: "Workspaces",
    render: (project) => (
      <div className="flex flex-wrap gap-2">
        <Link className="text-slate-900 underline" href={`/projects/${project.id}/quotes/builder`}>
          Quote
        </Link>
        <Link className="text-slate-900 underline" href={`/projects/${project.id}/forecast`}>
          Forecast
        </Link>
        <Link className="text-slate-900 underline" href={`/projects/${project.id}/comparables`}>
          Comparables
        </Link>
      </div>
    )
  }
];

function createEmptyProjectForm(): ProjectCreateFormValues {
  return {
    bidDueDate: "",
    code: "",
    description: "",
    endDate: "",
    name: "",
    quoteCurrencyCode: "",
    startDate: "",
    status: "bid"
  };
}

function toOptionalValue(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function toProjectSummary(project: ProjectRead): ProjectSummary {
  return {
    id: project.id,
    code: project.code ?? null,
    name: project.name,
    status: project.status,
    primaryClientName: null,
    quoteCurrencyCode: project.quoteCurrencyCode ?? null,
    updatedAt: project.updatedAt
  };
}

export function ProjectDirectory({ projects: initialProjects }: { projects: ProjectSummary[] }) {
  const api = getBrowserApiClient();
  const [projects, setProjects] = useState(initialProjects);
  const [query, setQuery] = useState("");
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<ProjectCreateFormValues>(() =>
    createEmptyProjectForm()
  );
  const [createError, setCreateError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isCreatePending, startCreateTransition] = useTransition();

  useEffect(() => {
    setProjects(initialProjects);
  }, [initialProjects]);

  useEffect(() => {
    if (!isCreateOpen) {
      return undefined;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isCreatePending) {
        setIsCreateOpen(false);
        setCreateError(null);
        setCreateForm(createEmptyProjectForm());
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isCreateOpen, isCreatePending]);

  const rows = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return projects;
    }

    return projects.filter((project) =>
      [project.name, project.code ?? "", project.primaryClientName ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(normalized)
    );
  }, [projects, query]);

  function closeCreateDialog() {
    if (isCreatePending) {
      return;
    }

    setIsCreateOpen(false);
    setCreateError(null);
    setCreateForm(createEmptyProjectForm());
  }

  function updateCreateForm(
    field: keyof ProjectCreateFormValues,
    value: ProjectCreateFormValues[keyof ProjectCreateFormValues]
  ) {
    setCreateForm((current) => ({
      ...current,
      [field]: value
    }));
    if (createError) {
      setCreateError(null);
    }
    if (successMessage) {
      setSuccessMessage(null);
    }
  }

  function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const validationError = validateProjectCreateForm(createForm);
    if (validationError) {
      setCreateError(validationError);
      return;
    }

    setCreateError(null);
    setSuccessMessage(null);

    startCreateTransition(() => {
      void api
        .createProject({
          name: createForm.name.trim(),
          status: createForm.status,
          code: toOptionalValue(createForm.code),
          description: toOptionalValue(createForm.description),
          quoteCurrencyCode: toOptionalValue(createForm.quoteCurrencyCode)?.toUpperCase() ?? null,
          startDate: toOptionalValue(createForm.startDate),
          endDate: toOptionalValue(createForm.endDate),
          bidDueDate: toOptionalValue(createForm.bidDueDate)
        })
        .then((project) => {
          setProjects((current) => [toProjectSummary(project), ...current]);
          setQuery("");
          setSuccessMessage(`Created project ${project.name}.`);
          setIsCreateOpen(false);
          setCreateForm(createEmptyProjectForm());
        })
        .catch((caughtError: unknown) => {
          setCreateError(
            caughtError instanceof ApiClientError
              ? caughtError.message
              : "Could not create the project."
          );
        });
    });
  }

  return (
    <>
      <SectionCard
        title="Projects"
        description="Operational project directory with direct links into quote, forecast, and comparable workflows."
        actions={
          <Button
            onClick={() => {
              setCreateError(null);
              setSuccessMessage(null);
              setIsCreateOpen(true);
            }}
            type="button"
            variant="primary"
          >
            + Add project
          </Button>
        }
      >
        <div className="space-y-4">
          {successMessage ? (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm text-emerald-900">
              {successMessage}
            </div>
          ) : null}
          <TableToolbar>
            <SearchInput
              className="max-w-sm"
              label="Search projects"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search project name, code, or client"
              value={query}
            />
          </TableToolbar>
          <DataTable
            columns={columns}
            emptyState={
              <EmptyState
                description="No projects matched the current filter."
                title="No projects found"
              />
            }
            rowKey={(project) => project.id}
            rows={rows}
          />
        </div>
      </SectionCard>

      {isCreateOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4 py-6"
          onClick={closeCreateDialog}
        >
          <div
            aria-labelledby="manual-project-intake-title"
            aria-modal="true"
            className="max-h-full w-full max-w-3xl overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-2xl"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
              <div className="space-y-1">
                <h2 className="text-lg font-semibold text-slate-950" id="manual-project-intake-title">
                  Manual project intake
                </h2>
                <p className="text-sm text-slate-600">
                  Register a project before a bid PDF is ready to import.
                </p>
              </div>
              <Button onClick={closeCreateDialog} type="button">
                Close
              </Button>
            </div>
            <form className="grid gap-4 px-5 py-4" onSubmit={handleCreateProject}>
              {createError ? (
                <ErrorState description={createError} title="Project creation failed" />
              ) : null}
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                Use this path when the project exists operationally but the bid has not been
                received or imported yet.
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <TextInput
                  autoFocus
                  label="Project name"
                  onChange={(event) => updateCreateForm("name", event.target.value)}
                  placeholder="Enter the working project name"
                  required
                  value={createForm.name}
                />
                <TextInput
                  label="Project code"
                  onChange={(event) => updateCreateForm("code", event.target.value)}
                  placeholder="Optional internal code"
                  value={createForm.code}
                />
                <SelectField
                  label="Status"
                  onChange={(event) =>
                    updateCreateForm("status", event.target.value as ProjectStatus)
                  }
                  value={createForm.status}
                >
                  {PROJECT_STATUS_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </SelectField>
                <TextInput
                  label="Quote currency"
                  maxLength={3}
                  onChange={(event) =>
                    updateCreateForm("quoteCurrencyCode", event.target.value.toUpperCase())
                  }
                  placeholder="GBP"
                  value={createForm.quoteCurrencyCode}
                />
                <TextInput
                  label="Bid due date"
                  onChange={(event) => updateCreateForm("bidDueDate", event.target.value)}
                  type="date"
                  value={createForm.bidDueDate}
                />
                <TextInput
                  label="Start date"
                  onChange={(event) => updateCreateForm("startDate", event.target.value)}
                  type="date"
                  value={createForm.startDate}
                />
                <TextInput
                  label="End date"
                  onChange={(event) => updateCreateForm("endDate", event.target.value)}
                  type="date"
                  value={createForm.endDate}
                />
              </div>
              <TextAreaField
                label="Description"
                onChange={(event) => updateCreateForm("description", event.target.value)}
                placeholder="Optional notes about the opportunity, scope, or current intake status"
                value={createForm.description}
              />
              <div className="flex flex-wrap justify-end gap-2 border-t border-slate-200 pt-4">
                <Button onClick={closeCreateDialog} type="button">
                  Cancel
                </Button>
                <Button disabled={isCreatePending} type="submit" variant="primary">
                  {isCreatePending ? "Creating..." : "Create project"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}
