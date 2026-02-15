"use client";

import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { Button } from "@/components/Button";
import { FeatureCard } from "@/components/Card";
import { MetricCard } from "@/components/MetricCard";

export default function LandingPage() {
  return (
    <div className="bg-acron-black text-white min-h-screen">
      <Navbar />

      {/* Hero */}
      <section className="pt-32 pb-20 px-6">
        <div className="max-w-7xl mx-auto grid md:grid-cols-2 gap-16 items-center">
          <div>
            <div className="text-sm font-medium text-acron-primary_accent mb-4 uppercase tracking-wide">
              Build intelligent inference
            </div>
            <h1 className="text-4xl md:text-5xl font-bold text-white mb-6 leading-tight">
              The inference optimizer for{" "}
              <span className="text-acron-primary_accent">cost efficiency</span>
            </h1>
            <p className="text-lg text-neutral-dark-gray mb-8 leading-relaxed">
              ACRON intelligently routes requests, caches semantically similar queries, and
              decomposes workflows to cut costs by 85–97%.
            </p>
            <div className="flex flex-wrap gap-4">
              <Link href="/signup">
                <Button variant="primary" size="lg">
                  Start Building
                </Button>
              </Link>
              <Link href="/getting-started">
                <Button variant="outline" size="lg">
                  Get Started
                </Button>
              </Link>
            </div>
          </div>
          <div className="bg-neutral-dark rounded-card border border-neutral-border p-12 h-80 flex items-center justify-center relative overflow-hidden group">
            {/* Graphical Loading Screen Placeholder / Logo Animation */}
             <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-acron-primary_accent/10 to-transparent opacity-0 group-hover:opacity-100 transition duration-700"></div>
            <div className="text-center text-neutral-dark-gray z-10">
               <div className="w-16 h-16 border-t-2 border-acron-primary_accent rounded-full animate-spin mb-4 mx-auto"></div>
              <p className="text-sm font-mono text-acron-primary_accent">ACRON ENGINE</p>
              <p className="text-xs mt-2 opacity-60">Initializing...</p>
            </div>
          </div>
        </div>
      </section>

      {/* Features - Why ACRON */}
      <section id="features" className="py-20 bg-neutral-dark px-6 border-y border-neutral-border">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center text-white mb-4">
            Why ACRON?
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
      <section id="metrics" className="py-20 bg-acron-black px-6">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center text-white mb-12">
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
      <section className="py-20 bg-acron-primary_accent px-6 relative overflow-hidden">
        <div className="absolute inset-0 bg-acron-black/10"></div>
        <div className="max-w-4xl mx-auto text-center text-white relative z-10">
          <h2 className="text-3xl md:text-4xl font-bold mb-6">
            Ready to optimize your LLM inference?
          </h2>
          <p className="mb-8 opacity-95 text-lg">
            Join companies reducing inference costs by 87% without compromising quality.
          </p>
          <Link href="/signup">
            <Button variant="secondary" size="lg" className="bg-white text-acron-primary_accent hover:bg-neutral-100">
              Start Building
            </Button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-neutral-dark text-neutral-dark-gray py-12 px-6 border-t border-neutral-border">
        <div className="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8">
          <div>
            <h4 className="font-semibold text-white mb-4">Products</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="/#features" className="hover:text-white transition-colors">Inference</Link></li>
              <li><Link href="/#features" className="hover:text-white transition-colors">Caching</Link></li>
              <li><Link href="/#features" className="hover:text-white transition-colors">Router</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Resources</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="/docs" className="hover:text-white transition-colors">Docs</a></li>
              <li><a href="/openapi.json" className="hover:text-white transition-colors">API Reference</a></li>
              <li><a href="#" className="hover:text-white transition-colors">Blog</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Company</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="/#metrics" className="hover:text-white transition-colors">About</Link></li>
              <li><Link href="/#pricing" className="hover:text-white transition-colors">Pricing</Link></li>
              <li><a href="#" className="hover:text-white transition-colors">Contact</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Follow</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="#" className="hover:text-white transition-colors">Twitter</a></li>
              <li><a href="#" className="hover:text-white transition-colors">GitHub</a></li>
              <li><a href="#" className="hover:text-white transition-colors">LinkedIn</a></li>
            </ul>
          </div>
        </div>
        <div className="max-w-7xl mx-auto mt-12 pt-8 border-t border-neutral-border flex flex-col md:flex-row justify-between items-center gap-4">
             <p className="text-sm">
              © {new Date().getFullYear()} ACRON. All rights reserved.
            </p>
             <div className="flex gap-4">
                 <div className="w-6 h-6 rounded-full bg-neutral-dark-gray/20"></div>
                 <div className="w-6 h-6 rounded-full bg-neutral-dark-gray/20"></div>
             </div>
        </div>
      </footer>
    </div>
  );
}
