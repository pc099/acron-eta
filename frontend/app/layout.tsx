import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Asahi – Inference Cost Optimizer",
  description: "Intelligent routing and caching to cut LLM inference costs by 85–97%.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
