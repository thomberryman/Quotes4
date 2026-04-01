"use client";

import { useMemo, useState } from "react";

import type { CounterpartyRead } from "@quotes4/contracts";

import { DataTable } from "@/components/data-table/data-table";
import { TableToolbar } from "@/components/data-table/table-toolbar";
import { SearchInput } from "@/components/forms/search-input";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import type { TableColumn } from "@/lib/navigation/types";

const columns: TableColumn<CounterpartyRead>[] = [
  {
    key: "name",
    header: "Client",
    render: (client) => (
      <div>
        <p className="font-medium text-slate-900">{client.name}</p>
        <p className="text-xs text-slate-500">{client.legalName ?? "No legal name recorded"}</p>
      </div>
    )
  },
  {
    key: "currency",
    header: "Currency",
    render: (client) => client.defaultCurrencyCode ?? "Not set"
  },
  {
    key: "classifications",
    header: "Classifications",
    render: (client) =>
      client.classifications.length > 0 ? client.classifications.join(", ") : "Unclassified"
  },
  {
    key: "status",
    header: "Status",
    render: (client) => <StatusBadge value={client.isActive ? "active" : "archived"} />
  }
];

export function ClientsTable({ clients }: { clients: CounterpartyRead[] }) {
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return clients;
    }

    return clients.filter((client) =>
      [client.name, client.legalName ?? "", client.websiteUrl ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(normalized)
    );
  }, [clients, query]);

  return (
    <SectionCard title="Clients" description="Counterparty records used across projects and quotes.">
      <TableToolbar>
        <SearchInput
          className="max-w-sm"
          label="Search clients"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search name, legal name, website"
          value={query}
        />
      </TableToolbar>
      <DataTable
        columns={columns}
        emptyState={
          <EmptyState
            description="No clients matched the current filter."
            title="No clients found"
          />
        }
        rowKey={(client) => client.id}
        rows={rows}
      />
    </SectionCard>
  );
}
