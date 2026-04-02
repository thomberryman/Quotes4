import { RevenuePhasingWorkspace } from "@/components/features/forecasts/revenue-phasing-workspace";
import { PageHeader } from "@/components/layout/page-header";
import { getForecastPhasingWorkspace } from "@/lib/api/forecasts";

function readSearchParam(
  value: string | string[] | undefined,
): string | undefined {
  if (typeof value === "string" && value.trim()) {
    return value;
  }

  if (Array.isArray(value)) {
    const firstValue = value.find(
      (item) => typeof item === "string" && item.trim(),
    );
    return firstValue;
  }

  return undefined;
}

export default async function RevenuePhasingPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const clientId = readSearchParam(params.clientId);
  const disciplineId = readSearchParam(params.disciplineId);
  const fromMonth = readSearchParam(params.fromMonth);
  const projectId = readSearchParam(params.projectId);
  const rowMode = readSearchParam(params.rowMode);
  const scenarioKey = readSearchParam(params.scenarioKey);
  const status = readSearchParam(params.status);
  const toMonth = readSearchParam(params.toMonth);
  const initialWorkspace = await getForecastPhasingWorkspace({
    ...(clientId ? { clientId } : {}),
    ...(disciplineId ? { disciplineId } : {}),
    ...(fromMonth ? { fromMonth } : {}),
    ...(projectId ? { projectId } : {}),
    ...(rowMode ? { rowMode } : {}),
    ...(scenarioKey ? { scenarioKey } : {}),
    ...(status ? { status } : {}),
    ...(toMonth ? { toMonth } : {}),
  });

  return (
    <>
      <PageHeader
        meta={{
          title: "Revenue Phasing",
          description:
            "Spreadsheet-style monthly revenue planning built on the live forecast allocation model.",
          breadcrumbs: [{ href: "/projects", label: "Projects" }],
        }}
      />
      <RevenuePhasingWorkspace initialWorkspace={initialWorkspace} />
    </>
  );
}
