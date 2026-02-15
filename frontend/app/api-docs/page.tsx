"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";

export default function ApiDocsPage() {
  const [apiUrl, setApiUrl] = useState("");
  useEffect(() => {
    if (typeof window !== "undefined") {
      setApiUrl(
        localStorage.getItem("acron_api_url") ||
        process.env.NEXT_PUBLIC_API_URL ||
        ""
      );
    }
  }, []);
  const docsUrl = apiUrl ? `${apiUrl.replace(/\/$/, "")}/docs` : "";
  return (
    <div className="min-h-screen bg-acron-black text-white">
      <Navbar />
      <main className="pt-24 px-6 pb-12 max-w-4xl mx-auto">
        <h1 className="text-2xl font-bold text-white mb-4">API Docs</h1>
        {docsUrl ? (
          <p className="text-neutral-dark-gray mb-4">
            OpenAPI (Swagger) docs:{" "}
            <a href={docsUrl} target="_blank" rel="noopener noreferrer" className="text-acron-primary_accent hover:underline">
              {docsUrl}
            </a>
          </p>
        ) : (
          <p className="text-neutral-dark-gray mb-4">
            Set your API base URL in{" "}
            <Link href="/settings" className="text-acron-primary_accent hover:underline">Settings</Link> or
            set <code className="bg-neutral-light-gray px-1 rounded text-white">NEXT_PUBLIC_API_URL</code> to see the docs link.
          </p>
        )}
        <p className="text-sm text-neutral-dark-gray">
          See also <code className="bg-neutral-light-gray px-1 rounded text-white">/openapi.json</code> for the raw schema.
        </p>
      </main>
    </div>
  );
}
