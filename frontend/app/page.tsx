"use client";

import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { Button } from "@/components/Button";
import { FeatureCard } from "@/components/Card";
import { MetricCard } from "@/components/MetricCard";

export default function LandingPage() {
  return (
    <div className="bg-neutral-white">
      <Navbar />

      {/* Hero */}
      <section className="pt-32 pb-20 bg-neutral-white px-6">
        <div className="max-w-7xl mx-auto grid md:grid-cols-2 gap-16 items-center">
          <div>
            <div className="text-sm font-medium text-asahi-orange mb-4 uppercase tracking-wide">
              Build intelligent inference
            </div>
            <h1 className="text-4xl md:text-5xl font-bold text-neutral-dark mb-6 leading-tight">
              The inference optimizer for{" "}
              <span className="text-asahi-orange">cost efficiency</span>
            </h1>
            <p className="text-lg text-neutral-dark-gray mb-8 leading-relaxed">
              ASAHI intelligently routes requests, caches semantically similar queries, and
              decomposes workflows to cut costs by 85–97%.
            </p>
            <div className="flex flex-wrap gap-4">
              <Link href="/signup">
                <Button variant="primary" size="lg">
                  Start Building
                </Button>
              </Link>
              <Link href="/dashboard">
                <Button variant="outline" size="lg">
                  Get Demo
                </Button>
              </Link>
            </div>
          </div>
          <div className="bg-asahi-orange-very-light rounded-card p-12 h-80 flex items-center justify-center">
            <div className="text-center text-neutral-dark-gray">
              <p className="text-sm">Architecture diagram</p>
              <p className="text-xs mt-2">(Isometric placeholder)</p>
            </div>
          </div>
        </div>
      </section>

      {/* Features - Why ASAHI */}
      <section id="features" className="py-20 bg-neutral-light-gray px-6">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center text-neutral-dark mb-4">
            Why ASAHI?
          </h2>
          <p className="text-center text-neutral-dark-gray mb-12">
            Three intelligent caching layers
          </p>
          <div className="grid md:grid-cols-3 gap-8">
            <FeatureCard
              icon="🔄"
              title="Tier 1: Exact Match"
              description="Instant hits for identical requests. Zero cost, instant response."
            />
            <FeatureCard
              icon="🧠"
              title="Tier 2: Semantic Similarity"
              description="Detect similar queries at 85%+ similarity. Return cached result with minimal cost."
              highlight
            />
            <FeatureCard
              icon="📦"
              title="Tier 3: Intermediate Results"
              description="Cache workflow intermediate steps. Reuse across multiple requests."
            />
          </div>
        </div>
      </section>

      {/* Metrics - Production Results */}
      <section id="metrics" className="py-20 bg-neutral-white px-6">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center text-neutral-dark mb-12">
            Production Results
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <MetricCard value="87" label="Cost Savings" unit="%" highlight />
            <MetricCard value="150" label="Latency Reduction" unit="ms" />
            <MetricCard value="98" label="Accuracy" unit="%" />
            <MetricCard value="4.8" label="Quality Score" unit="/5.0" />
          </div>
        </div>
      </section>

      {/* Pricing link target */}
      <section id="pricing" className="sr-only" aria-hidden />

      {/* CTA */}
      <section className="py-20 bg-asahi-orange px-6">
        <div className="max-w-4xl mx-auto text-center text-white">
          <h2 className="text-3xl md:text-4xl font-bold mb-6">
            Ready to optimize your LLM inference?
          </h2>
          <p className="mb-8 opacity-95">
            Join companies reducing inference costs by 87% without compromising quality.
          </p>
          <Link href="/signup">
            <Button variant="secondary" size="lg">
              Start Building
            </Button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-[#1A1A1A] text-neutral-border py-12 px-6">
        <div className="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8">
          <div>
            <h4 className="font-semibold text-white mb-4">Products</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="/#features" className="hover:text-white">Inference</Link></li>
              <li><Link href="/#features" className="hover:text-white">Caching</Link></li>
              <li><Link href="/#features" className="hover:text-white">Router</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Resources</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="/docs" className="hover:text-white">Docs</a></li>
              <li><a href="/openapi.json" className="hover:text-white">API Reference</a></li>
              <li><a href="#" className="hover:text-white">Blog</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Company</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="/#metrics" className="hover:text-white">About</Link></li>
              <li><Link href="/#pricing" className="hover:text-white">Pricing</Link></li>
              <li><a href="#" className="hover:text-white">Contact</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Follow</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="#" className="hover:text-white">Twitter</a></li>
              <li><a href="#" className="hover:text-white">GitHub</a></li>
              <li><a href="#" className="hover:text-white">LinkedIn</a></li>
            </ul>
          </div>
        </div>
        <p className="text-center text-sm mt-12 text-neutral-dark-gray">
          © {new Date().getFullYear()} ASAHI. All rights reserved.
        </p>
      </footer>
    </div>
  );
}
