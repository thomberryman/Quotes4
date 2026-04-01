import { ClientsTable } from "@/components/features/clients/clients-table";
import { PageHeader } from "@/components/layout/page-header";
import { listClients } from "@/lib/api/directories";

export default async function ClientsPage() {
  const response = await listClients();

  return (
    <>
      <PageHeader
        meta={{
          title: "Clients",
          description: "Counterparty records used in project setup, quote ownership, and historical reporting."
        }}
      />
      <ClientsTable clients={response.items} />
    </>
  );
}
