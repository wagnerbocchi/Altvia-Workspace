import { QueueMembersScreen } from "@/components/service-desk/screens";

export default async function QueueMembersPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <QueueMembersScreen id={id} />;
}
