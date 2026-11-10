import { ContactScreen } from "@/components/client-workspace/screens";

export default async function ContactsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ContactScreen id={id} />;
}
