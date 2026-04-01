import { ContactsTable } from "@/components/features/clients/contacts-table";
import { PageHeader } from "@/components/layout/page-header";
import { listContacts } from "@/lib/api/directories";

export default async function ContactsPage() {
  const response = await listContacts();

  return (
    <>
      <PageHeader
        meta={{
          title: "Contacts",
          description: "Shared contact directory used across counterparties and project workspaces."
        }}
      />
      <ContactsTable contacts={response.items} />
    </>
  );
}
