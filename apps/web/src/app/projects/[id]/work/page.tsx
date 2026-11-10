import { WorkDirectoryScreen } from "@/components/work-items/screens";

export default async function WorkPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <WorkDirectoryScreen project={id} />;
}
