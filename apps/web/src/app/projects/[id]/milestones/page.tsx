import { MilestonesScreen } from "@/components/project-workspace/screens";
export default async function MilestonesPage({ params }: { params: Promise<{ id: string }> }) {
  return <MilestonesScreen id={(await params).id} />;
}
