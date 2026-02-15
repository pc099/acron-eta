"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await login({ email, password });
      if (res.api_key) {
        if (typeof window !== "undefined") {
          localStorage.setItem("acron_api_key", res.api_key);
        }
        router.push("/dashboard");
      } else {
        setError("Login failed: No API key returned.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* Left: white form panel (~60%) */}
      <div className="w-full lg:w-[58%] min-h-screen bg-white flex flex-col items-center justify-center p-8">
        <Link href="/" className="absolute top-6 left-8 flex items-center gap-2">
          <img src="/logo.svg" alt="ACRON" className="w-8 h-8 rounded object-contain" />
          <span className="text-xl font-bold text-neutral-800 tracking-wide">ACRON</span>
        </Link>

        <div className="w-full max-w-sm mx-auto">
          <h1 className="text-2xl font-bold text-neutral-900 mb-1">Welcome back</h1>
          <p className="text-neutral-500 text-sm mb-8">Sign in to your ACRON dashboard</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Email"
              type="email"
              placeholder="yours@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              variant="light"
            />
            <Input
              label="Password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              variant="light"
            />

            {error && (
              <div className="p-3 rounded bg-red-50 border border-red-200 text-red-700 text-sm">
                {error}
              </div>
            )}

            <Button
              variant="primary"
              type="submit"
              className="w-full justify-center mt-4"
              disabled={loading}
            >
              {loading ? "Signing in…" : "Continue →"}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-neutral-500">
            Don&apos;t have an account?{" "}
            <Link href="/signup" className="text-acron-primary_accent font-medium hover:underline">
              Sign up
            </Link>
          </p>
        </div>

        <p className="absolute bottom-6 left-8 right-8 text-center text-xs text-neutral-400">
          By signing in, you agree to our Terms of Service and Privacy Policy.
        </p>
      </div>

      {/* Right: dark panel (~40%) - tagline */}
      <div className="hidden lg:flex lg:w-[42%] min-h-screen bg-acron-black flex-col items-center justify-center px-12 text-center">
        <p className="text-acron-primary_accent text-sm font-medium uppercase tracking-widest mb-4">
          Build intelligent inference
        </p>
        <h2 className="text-3xl md:text-4xl font-bold text-white leading-tight max-w-md">
          The inference optimizer for scale in production
        </h2>
      </div>
    </div>
  );
}
