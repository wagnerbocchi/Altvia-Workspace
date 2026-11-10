import { QueuesScreen } from "@/components/service-desk/screens";

export default async function QueuePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <QueuesScreen id={id} />;
}
