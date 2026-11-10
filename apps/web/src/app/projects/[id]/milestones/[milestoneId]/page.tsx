import { MilestonesScreen } from "@/components/project-workspace/screens";
export default async function MilestonePage({ params }: { params: Promise<{ id: string; milestoneId: string }> }) {
  const { id, milestoneId } = await params;
  return <MilestonesScreen id={id} milestoneId={milestoneId} />;
}
