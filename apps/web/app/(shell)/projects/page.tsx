import { ProjectDirectory } from "@/components/features/projects/project-directory";
import { PageHeader } from "@/components/layout/page-header";
import { listProjects } from "@/lib/api/projects";

export default async function ProjectsPage() {
  const response = await listProjects();

  return (
    <>
      <PageHeader
        meta={{
          title: "Projects",
          description: "Primary operational list for bid, awarded, active, and archived work."
        }}
      />
      <ProjectDirectory projects={response.items} />
    </>
  );
}
