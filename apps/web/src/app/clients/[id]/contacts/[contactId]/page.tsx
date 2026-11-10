import { ContactScreen } from "@/components/client-workspace/screens";

export default async function ContactPage({ params }: { params: Promise<{ id: string; contactId: string }> }) {
  const { id, contactId } = await params;
  return <ContactScreen id={id} contactId={contactId} />;
}
