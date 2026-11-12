import { MailCasesScreen } from "@/components/mail-cases/screens";

export default async function MailCasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <MailCasesScreen id={id} />;
}
