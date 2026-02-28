import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { dark } from "@clerk/themes";
import { Toaster } from "sonner";
import { QueryProvider } from "@/components/providers/query-provider";
import { AuthSetup } from "@/components/providers/auth-setup";
import "./globals.css";

export const metadata: Metadata = {
  title: "ASAHI - LLM Inference Cost Optimizer",
  description:
    "Intelligent routing and caching to cut LLM inference costs by 85-97%. Drop-in OpenAI replacement.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <ClerkProvider
      appearance={{
        baseTheme: dark,
        variables: {
          colorPrimary: "#FF6B35",
          colorBackground: "#121212",
          colorInputBackground: "#1a1a1a",
          colorInputText: "#f5f5f5",
          colorText: "#f5f5f5",
          colorTextSecondary: "#a3a3a3",
          colorNeutral: "#f5f5f5",
        },
      }}
    >
      <html lang="en" className="dark">
        <body className="antialiased min-h-screen bg-background text-foreground">
          <QueryProvider>
            <AuthSetup />
            {children}
            <Toaster richColors position="top-right" />
          </QueryProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}
