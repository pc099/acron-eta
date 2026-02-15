"use client";

import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";

export default function GettingStartedPage() {
  return (
    <div className="bg-acron-black text-white min-h-screen">
      <Navbar />

      <section className="pt-28 pb-16 px-6">
        <div className="max-w-3xl mx-auto">
          <p className="text-sm font-medium text-acron-primary_accent uppercase tracking-wide mb-2">
            Get Started
          </p>
          <h1 className="text-4xl md:text-5xl font-bold text-white mb-6 leading-tight">
            Start optimizing inference in minutes
          </h1>
          <p className="text-lg text-neutral-dark-gray mb-10 leading-relaxed">
            ACRON reduces LLM inference costs by 85–97% through intelligent routing,
            semantic caching, and workflow decomposition. Follow these steps to get going.
          </p>

          <div className="space-y-6">
            <Card className="border-neutral-border bg-neutral-dark p-6">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-full bg-acron-primary_accent/20 flex items-center justify-center flex-shrink-0 text-acron-primary_accent font-bold">
                  1
                </div>
                <div>
                  <h2 className="text-xl font-bold text-white mb-2">Create an account</h2>
                  <p className="text-neutral-dark-gray mb-4">
                    Sign up to get your API key and access the dashboard.
                  </p>
                  <Link href="/signup">
                    <Button variant="primary">Sign Up</Button>
                  </Link>
                </div>
              </div>
            </Card>

            <Card className="border-neutral-border bg-neutral-dark p-6">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-full bg-acron-primary_accent/20 flex items-center justify-center flex-shrink-0 text-acron-primary_accent font-bold">
                  2
                </div>
                <div>
                  <h2 className="text-xl font-bold text-white mb-2">Run your first inference</h2>
                  <p className="text-neutral-dark-gray mb-4">
                    Use the Inference tab to send a prompt and see routing, cost, and cache behavior.
                  </p>
                  <Link href="/inference">
                    <Button variant="outline" className="border-neutral-border text-white hover:bg-neutral-light-gray">
                      Go to Inference
                    </Button>
                  </Link>
                </div>
              </div>
            </Card>

            <Card className="border-neutral-border bg-neutral-dark p-6">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-full bg-acron-primary_accent/20 flex items-center justify-center flex-shrink-0 text-acron-primary_accent font-bold">
                  3
                </div>
                <div>
                  <h2 className="text-xl font-bold text-white mb-2">Integrate via API</h2>
                  <p className="text-neutral-dark-gray mb-4">
                    Use your API key with the REST API or OpenAI-compatible endpoint. See API Docs for details.
                  </p>
                  <Link href="/api-docs">
                    <Button variant="outline" className="border-neutral-border text-white hover:bg-neutral-light-gray">
                      API Docs
                    </Button>
                  </Link>
                </div>
              </div>
            </Card>
          </div>

          <div className="mt-12 text-center">
            <p className="text-neutral-dark-gray mb-4">Already have an account?</p>
            <Link href="/login">
              <Button variant="ghost" className="text-acron-primary_accent hover:text-white">
                Sign In
              </Button>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
