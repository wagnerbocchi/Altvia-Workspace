import { TicketsScreen } from "@/components/tickets/screens";

export default async function TicketPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TicketsScreen id={id} />;
}
