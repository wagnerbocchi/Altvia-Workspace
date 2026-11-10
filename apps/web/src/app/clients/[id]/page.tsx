import { ClientDetailScreen } from "@/components/client-workspace/screens";

export default async function ClientPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ClientDetailScreen id={id} />;
}
