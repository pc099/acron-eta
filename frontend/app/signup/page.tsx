"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Card } from "@/components/Card";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { signup } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [orgName, setOrgName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await signup({ email, password, full_name: fullName, org_name: orgName });
      if (res.api_key) {
        if (typeof window !== "undefined") {
          localStorage.setItem("acron_api_key", res.api_key);
        }
        router.push("/dashboard");
      } else {
        setError("Signup failed: No API key returned.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-acron-black flex flex-col items-center justify-center p-6">
      <Link href="/" className="mb-8 flex items-center gap-2">
        <img src="/logo.svg" alt="ACRON" className="w-8 h-8 rounded object-contain" />
        <span className="text-2xl font-bold text-white tracking-wide">ACRON</span>
      </Link>

      <Card className="w-full max-w-md border-neutral-border bg-neutral-dark">
        <h1 className="text-2xl font-bold text-white mb-2 text-center">Create Account</h1>
        <p className="text-neutral-dark-gray text-center mb-8">
          Start optimizing your inference costs
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Full Name"
            placeholder="John Doe"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="bg-neutral-dark border-neutral-border text-white placeholder-neutral-dark-gray focus:border-acron-primary_accent"
          />
          <Input
            label="Email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="bg-neutral-dark border-neutral-border text-white placeholder-neutral-dark-gray focus:border-acron-primary_accent"
          />
          <Input
            label="Password"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="bg-neutral-dark border-neutral-border text-white placeholder-neutral-dark-gray focus:border-acron-primary_accent"
          />
          <Input
            label="Organization Name (Optional)"
            placeholder="Acme Corp"
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            className="bg-neutral-dark border-neutral-border text-white placeholder-neutral-dark-gray focus:border-acron-primary_accent"
          />

          {error && (
            <div className="p-3 rounded bg-red-900/20 border border-semantic-error text-semantic-error text-sm">
              {error}
            </div>
          )}

          <Button
            variant="primary"
            className="w-full justify-center mt-6"
            disabled={loading}
          >
            {loading ? "Creating Account..." : "Sign Up"}
          </Button>
        </form>

        <div className="mt-6 text-center text-sm text-neutral-dark-gray">
          Already have an account?{" "}
          <Link href="/login" className="text-acron-primary_accent hover:text-white transition">
            Sign in
          </Link>
        </div>
      </Card>
    </div>
  );
}
