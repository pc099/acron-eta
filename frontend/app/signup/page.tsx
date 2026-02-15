"use client";

import { useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { signup } from "@/lib/api";

export default function SignupPage() {
  const [orgName, setOrgName] = useState("");
  const [userId, setUserId] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{
    org_id: string;
    api_key: string;
    org_name: string;
    message: string;
  } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setResult(null);
    if (!orgName.trim() || !userId.trim()) {
      setError("Organization name and user ID are required.");
      return;
    }
    setLoading(true);
    try {
      const data = await signup(orgName.trim(), userId.trim(), email.trim() || undefined);
      setResult(data);
      if (typeof window !== "undefined") {
        localStorage.setItem("asahi_api_key", data.api_key);
        localStorage.setItem("asahi_org_id", data.org_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-neutral-white">
      <Navbar />
      <main className="pt-28 pb-16 px-6 max-w-md mx-auto">
        <h1 className="text-2xl font-bold text-neutral-dark mb-2">Create your account</h1>
        <p className="text-neutral-dark-gray mb-8">
          Get an API key and start optimizing inference costs.
        </p>
        {result ? (
          <div className="rounded-card border border-semantic-success bg-green-50 p-6">
            <p className="font-medium text-neutral-dark mb-2">Account created</p>
            <p className="text-sm text-neutral-dark-gray mb-4">{result.message}</p>
            <p className="text-xs text-neutral-dark-gray">
              <strong>Org ID:</strong> {result.org_id}
            </p>
            <p className="text-xs text-neutral-dark-gray mt-1">
              <strong>API key:</strong> Saved to this browser. Use Settings to view or change it.
            </p>
            <Link href="/dashboard" className="mt-6 inline-block">
              <Button variant="primary">Go to Dashboard</Button>
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <Input
              label="Organization name"
              placeholder="Acme Corp"
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              required
            />
            <Input
              label="User ID"
              placeholder="dev1"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              required
            />
            <Input
              label="Email (optional)"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            {error && (
              <p className="text-sm text-semantic-error mb-4">{error}</p>
            )}
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? "Creating…" : "Sign Up"}
            </Button>
          </form>
        )}
        <p className="mt-8 text-center text-sm text-neutral-dark-gray">
          Already have an key?{" "}
          <Link href="/dashboard" className="text-asahi-orange hover:underline">
            Go to Dashboard
          </Link>{" "}
          and set it in Settings.
        </p>
      </main>
    </div>
  );
}
