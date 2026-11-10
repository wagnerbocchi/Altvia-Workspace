import { ProjectDetailScreen } from "@/components/project-workspace/screens";

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProjectDetailScreen id={id} />;
}
