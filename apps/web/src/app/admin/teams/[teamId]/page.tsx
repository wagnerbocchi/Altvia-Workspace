import { TeamDetailScreen } from "@/components/team-admin/screens";

export default async function TeamPage({ params }: { params: Promise<{ teamId: string }> }) {
  return <TeamDetailScreen id={(await params).teamId} />;
}
