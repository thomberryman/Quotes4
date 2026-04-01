"use client";

import { useMemo, useState } from "react";

import type { ContactRead } from "@quotes4/contracts";

import { DataTable } from "@/components/data-table/data-table";
import { TableToolbar } from "@/components/data-table/table-toolbar";
import { SearchInput } from "@/components/forms/search-input";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import type { TableColumn } from "@/lib/navigation/types";

const columns: TableColumn<ContactRead>[] = [
  {
    key: "name",
    header: "Contact",
    render: (contact) => (
      <div>
        <p className="font-medium text-slate-900">{contact.fullName}</p>
        <p className="text-xs text-slate-500">{contact.email ?? "No email recorded"}</p>
      </div>
    )
  },
  {
    key: "phone",
    header: "Phone",
    render: (contact) => contact.mobile ?? contact.phone ?? "Not set"
  },
  {
    key: "notes",
    header: "Notes",
    render: (contact) => contact.notes ?? "No notes"
  },
  {
    key: "status",
    header: "Status",
    render: (contact) => <StatusBadge value={contact.isActive ? "active" : "archived"} />
  }
];

export function ContactsTable({ contacts }: { contacts: ContactRead[] }) {
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return contacts;
    }

    return contacts.filter((contact) =>
      [contact.fullName, contact.email ?? "", contact.phone ?? "", contact.mobile ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(normalized)
    );
  }, [contacts, query]);

  return (
    <SectionCard title="Contacts" description="People records shared across counterparties and project teams.">
      <TableToolbar>
        <SearchInput
          className="max-w-sm"
          label="Search contacts"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search name, email, phone"
          value={query}
        />
      </TableToolbar>
      <DataTable
        columns={columns}
        emptyState={
          <EmptyState
            description="No contacts matched the current filter."
            title="No contacts found"
          />
        }
        rowKey={(contact) => contact.id}
        rows={rows}
      />
    </SectionCard>
  );
}
