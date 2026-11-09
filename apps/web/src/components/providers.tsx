"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState } from "react";

export function createAppQueryClient() {
  return new QueryClient({ defaultOptions: {
    queries: { retry: false, staleTime: 0, gcTime: 0, refetchOnWindowFocus: "always" },
    mutations: { retry: false, gcTime: 0 },
  } });
}

export function Providers({ children, nonce }: { children: React.ReactNode; nonce: string }) {
  const [client] = useState(createAppQueryClient);
  return <ThemeProvider nonce={nonce} attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  </ThemeProvider>;
}
