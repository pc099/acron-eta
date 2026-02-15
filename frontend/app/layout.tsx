import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Acron – Inference Cost Optimizer",
  description: "Intelligent routing and caching to cut LLM inference costs by 85–97%.",
};

import LoadingScreen from "@/components/LoadingScreen";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased bg-black text-white">
        <LoadingScreen />
        {children}
      </body>
    </html>
  );
}
