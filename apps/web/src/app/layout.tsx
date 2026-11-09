import type { Metadata } from "next";
import { headers } from "next/headers";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Altvia Workspace", description: "Acesso ao ambiente de trabalho Altvia.",
  robots: { index: false, follow: false },
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const nonce = (await headers()).get("x-nonce") ?? "";
  return <html lang="pt-BR" suppressHydrationWarning><body><Providers nonce={nonce}>{children}</Providers></body></html>;
}
