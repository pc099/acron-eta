"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export default function LandingPage() {
  const [engineStatus, setEngineStatus] = useState<
    "checking" | "ready" | "offline"
  >("checking");

  useEffect(() => {
    const base = process.env.NEXT_PUBLIC_API_URL || "";
    if (!base) {
      setEngineStatus("ready");
      return;
    }
    fetch(`${base.replace(/\/$/, "")}/health`, { method: "GET" })
      .then((r) => setEngineStatus(r.ok ? "ready" : "offline"))
      .catch(() => setEngineStatus("offline"));
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Navbar */}
      <nav className="fixed top-0 inset-x-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <Link href="/" className="text-xl font-bold tracking-tight">
            <span className="text-asahi">ASAHI</span>
          </Link>
          <div className="hidden items-center gap-8 md:flex">
            <a
              href="#features"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Features
            </a>
            <a
              href="#metrics"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Results
            </a>
            <a
              href="#pricing"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Pricing
            </a>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/sign-in"
              className="rounded-lg px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              Sign In
            </Link>
            <Link
              href="/sign-up"
              className="rounded-lg bg-asahi px-4 py-2 text-sm font-medium text-white hover:bg-asahi-dark transition-colors"
            >
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-20 px-6">
        <div className="mx-auto grid max-w-7xl items-center gap-16 md:grid-cols-2">
          <div>
            <div className="mb-4 text-sm font-medium uppercase tracking-wide text-asahi">
              Build intelligent inference
            </div>
            <h1 className="mb-6 text-4xl font-bold leading-tight text-foreground md:text-5xl">
              The inference optimizer for{" "}
              <span className="text-asahi">cost efficiency</span>
            </h1>
            <p className="mb-8 text-lg leading-relaxed text-muted-foreground">
              ASAHI intelligently routes requests, caches semantically similar
              queries, and decomposes workflows to cut costs by 85-97%.
            </p>
            <div className="flex flex-wrap gap-4">
              <Link
                href="/sign-up"
                className="rounded-lg bg-asahi px-6 py-3 text-sm font-medium text-white hover:bg-asahi-dark transition-colors"
              >
                Start Building
              </Link>
              <a
                href="#features"
                className="rounded-lg border border-border px-6 py-3 text-sm font-medium text-foreground hover:bg-muted transition-colors"
              >
                Learn More
              </a>
            </div>
          </div>
          <div className="group relative flex h-80 items-center justify-center overflow-hidden rounded-xl border border-border bg-card p-12">
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-asahi/10 to-transparent opacity-0 transition duration-700 group-hover:opacity-100" />
            <div className="z-10 text-center">
              {engineStatus === "checking" && (
                <>
                  <div className="mx-auto mb-4 h-16 w-16 animate-spin rounded-full border-t-2 border-asahi" />
                  <p className="text-sm font-mono text-asahi">ASAHI ENGINE</p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Checking...
                  </p>
                </>
              )}
              {engineStatus === "ready" && (
                <>
                  <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full border-2 border-asahi bg-asahi/20">
                    <span className="text-2xl text-asahi">&#10003;</span>
                  </div>
                  <p className="text-sm font-mono text-asahi">ASAHI ENGINE</p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Ready to optimize
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground/80">
                    Sign in or sign up to use the dashboard
                  </p>
                </>
              )}
              {engineStatus === "offline" && (
                <>
                  <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full border border-border bg-muted">
                    <span className="text-xl text-muted-foreground">&#8635;</span>
                  </div>
                  <p className="text-sm font-mono text-asahi">ASAHI ENGINE</p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Configure API URL in Settings to check status
                  </p>
                </>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section
        id="features"
        className="border-y border-border bg-card px-6 py-20"
      >
        <div className="mx-auto max-w-7xl">
          <h2 className="mb-4 text-center text-3xl font-bold text-foreground md:text-4xl">
            Why ASAHI?
          </h2>
          <p className="mb-12 text-center text-muted-foreground">
            Three intelligent caching layers
          </p>
          <div className="grid gap-8 md:grid-cols-3">
            {[
              {
                icon: "\uD83D\uDD04",
                title: "Tier 1: Exact Match",
                description:
                  "Instant hits for identical requests. Zero cost, instant response.",
              },
              {
                icon: "\uD83E\uDDE0",
                title: "Tier 2: Semantic Similarity",
                description:
                  "Detect similar queries at 85%+ similarity. Return cached result with minimal cost.",
                highlight: true,
              },
              {
                icon: "\uD83D\uDCE6",
                title: "Tier 3: Intermediate Results",
                description:
                  "Cache workflow intermediate steps. Reuse across multiple requests.",
              },
            ].map((feature) => (
              <div
                key={feature.title}
                className={`rounded-xl border p-6 transition-colors ${
                  feature.highlight
                    ? "border-asahi/50 bg-asahi/5"
                    : "border-border bg-background hover:border-asahi/30"
                }`}
              >
                <div className="mb-4 text-3xl">{feature.icon}</div>
                <h3 className="mb-2 text-lg font-semibold text-foreground">
                  {feature.title}
                </h3>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Metrics */}
      <section id="metrics" className="px-6 py-20">
        <div className="mx-auto max-w-7xl">
          <h2 className="mb-12 text-center text-3xl font-bold text-foreground md:text-4xl">
            Production Results
          </h2>
          <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
            {[
              { value: "87%", label: "Cost Savings", highlight: true },
              { value: "150ms", label: "Latency Reduction" },
              { value: "98%", label: "Accuracy" },
              { value: "4.8/5.0", label: "Quality Score" },
            ].map((metric) => (
              <div
                key={metric.label}
                className="rounded-xl border border-border bg-card p-6 text-center"
              >
                <p
                  className={`text-3xl font-bold ${
                    metric.highlight ? "text-asahi" : "text-foreground"
                  }`}
                >
                  {metric.value}
                </p>
                <p className="mt-2 text-sm text-muted-foreground">
                  {metric.label}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing anchor */}
      <section id="pricing" className="sr-only" aria-hidden />

      {/* CTA */}
      <section className="relative overflow-hidden bg-asahi px-6 py-20">
        <div className="absolute inset-0 bg-black/10" />
        <div className="relative z-10 mx-auto max-w-4xl text-center text-white">
          <h2 className="mb-6 text-3xl font-bold md:text-4xl">
            Ready to optimize your LLM inference?
          </h2>
          <p className="mb-8 text-lg opacity-95">
            Join companies reducing inference costs by 87% without compromising
            quality.
          </p>
          <Link
            href="/sign-up"
            className="inline-block rounded-lg bg-white px-6 py-3 text-sm font-medium text-asahi-dark hover:bg-neutral-100 transition-colors"
          >
            Start Building
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border bg-card px-6 py-12 text-muted-foreground">
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-8 md:grid-cols-4">
          <div>
            <h4 className="mb-4 font-semibold text-foreground">Products</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <a href="#features" className="hover:text-foreground transition-colors">
                  Inference
                </a>
              </li>
              <li>
                <a href="#features" className="hover:text-foreground transition-colors">
                  Caching
                </a>
              </li>
              <li>
                <a href="#features" className="hover:text-foreground transition-colors">
                  Router
                </a>
              </li>
            </ul>
          </div>
          <div>
            <h4 className="mb-4 font-semibold text-foreground">Resources</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <a href="/docs" className="hover:text-foreground transition-colors">
                  Docs
                </a>
              </li>
              <li>
                <a
                  href="/openapi.json"
                  className="hover:text-foreground transition-colors"
                >
                  API Reference
                </a>
              </li>
              <li>
                <a href="#" className="hover:text-foreground transition-colors">
                  Blog
                </a>
              </li>
            </ul>
          </div>
          <div>
            <h4 className="mb-4 font-semibold text-foreground">Company</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <a href="#metrics" className="hover:text-foreground transition-colors">
                  About
                </a>
              </li>
              <li>
                <a href="#pricing" className="hover:text-foreground transition-colors">
                  Pricing
                </a>
              </li>
              <li>
                <a href="#" className="hover:text-foreground transition-colors">
                  Contact
                </a>
              </li>
            </ul>
          </div>
          <div>
            <h4 className="mb-4 font-semibold text-foreground">Follow</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <a href="#" className="hover:text-foreground transition-colors">
                  Twitter
                </a>
              </li>
              <li>
                <a href="#" className="hover:text-foreground transition-colors">
                  GitHub
                </a>
              </li>
              <li>
                <a href="#" className="hover:text-foreground transition-colors">
                  LinkedIn
                </a>
              </li>
            </ul>
          </div>
        </div>
        <div className="mx-auto mt-12 flex max-w-7xl flex-col items-center justify-between gap-4 border-t border-border pt-8 md:flex-row">
          <p className="text-sm">
            &copy; {new Date().getFullYear()} ASAHI. All rights reserved.
          </p>
          <div className="flex gap-4">
            <div className="h-6 w-6 rounded-full bg-muted" />
            <div className="h-6 w-6 rounded-full bg-muted" />
          </div>
        </div>
      </footer>
    </div>
  );
}
