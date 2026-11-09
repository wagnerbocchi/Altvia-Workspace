import { AccountDetailScreen } from "@/components/user-admin/screens";

export default async function AccountPage({ params }: { params: Promise<{ userId: string }> }) {
  return <AccountDetailScreen id={(await params).userId} />;
}
