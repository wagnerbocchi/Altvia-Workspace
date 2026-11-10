import { ProjectMembersScreen } from "@/components/project-workspace/screens";

export default async function ProjectMembersPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProjectMembersScreen id={id} />;
}
