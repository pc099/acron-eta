"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Check,
  ChevronRight,
  Copy,
  Package,
  Key,
  Zap,
  TrendingDown,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const steps = [
  {
    title: "Install the SDK",
    description: "Add the ASAHI Python SDK to your project",
    icon: Package,
  },
  {
    title: "Get your API Key",
    description: "Configure authentication for your application",
    icon: Key,
  },
  {
    title: "Make your first request",
    description: "Send an inference request through ASAHI",
    icon: Zap,
  },
  {
    title: "Watch your savings",
    description: "Monitor cost optimization on your dashboard",
    icon: TrendingDown,
  },
] as const;

const codeSnippets: Record<number, string> = {
  0: `pip install asahi-ai`,
  1: `import asahi

client = asahi.Client(
    api_key="your-api-key-here",
)`,
  2: `response = client.chat.completions.create(
    messages=[
        {"role": "user", "content": "What is Python?"}
    ],
    routing_mode="AUTOPILOT",
)

print(response.choices[0].message.content)
print(f"Saved: ${response.asahi.savings_usd:.4f}")`,
};

export default function OnboardingPage({
  params,
}: {
  params: { orgSlug: string };
}) {
  const [currentStep, setCurrentStep] = useState(0);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success("Copied to clipboard");
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            Getting Started
          </h1>
          <p className="text-sm text-muted-foreground">
            Set up ASAHI in a few simple steps
          </p>
        </div>
        <Link
          href={`/${params.orgSlug}/dashboard`}
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          Skip setup
        </Link>
      </div>

      {/* Progress indicator */}
      <div className="flex items-center gap-2">
        {steps.map((step, index) => (
          <div key={index} className="flex items-center gap-2">
            <button
              onClick={() => setCurrentStep(index)}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium transition-colors",
                index < currentStep
                  ? "bg-green-500 text-white"
                  : index === currentStep
                    ? "bg-asahi text-white"
                    : "border border-border bg-background text-muted-foreground"
              )}
            >
              {index < currentStep ? (
                <Check className="h-4 w-4" />
              ) : (
                index + 1
              )}
            </button>
            {index < steps.length - 1 && (
              <div
                className={cn(
                  "h-0.5 w-8 sm:w-16 transition-colors",
                  index < currentStep ? "bg-green-500" : "bg-border"
                )}
              />
            )}
          </div>
        ))}
      </div>

      {/* Step content */}
      <div className="rounded-lg border border-border bg-card p-8 shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          {(() => {
            const Icon = steps[currentStep].icon;
            return (
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-asahi/20">
                <Icon className="h-5 w-5 text-asahi" />
              </div>
            );
          })()}
          <div>
            <h2 className="text-lg font-semibold text-foreground">
              {steps[currentStep].title}
            </h2>
            <p className="text-sm text-muted-foreground">
              {steps[currentStep].description}
            </p>
          </div>
        </div>

        {/* Step 0: Install SDK */}
        {currentStep === 0 && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Install the ASAHI SDK using pip:
            </p>
            <div className="relative">
              <pre className="overflow-x-auto rounded-md border border-border bg-background p-4 font-mono text-sm text-foreground">
                {codeSnippets[0]}
              </pre>
              <button
                onClick={() => copyToClipboard(codeSnippets[0])}
                className="absolute right-3 top-3 rounded-md border border-border p-1.5 text-muted-foreground hover:text-foreground transition-colors"
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* Step 1: Get API Key */}
        {currentStep === 1 && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Create an API key from the{" "}
              <Link
                href={`/${params.orgSlug}/keys`}
                className="text-asahi hover:underline"
              >
                API Keys page
              </Link>
              , then initialize the client:
            </p>
            <div className="relative">
              <pre className="overflow-x-auto rounded-md border border-border bg-background p-4 font-mono text-sm text-foreground">
                {codeSnippets[1]}
              </pre>
              <button
                onClick={() => copyToClipboard(codeSnippets[1])}
                className="absolute right-3 top-3 rounded-md border border-border p-1.5 text-muted-foreground hover:text-foreground transition-colors"
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="rounded-md border border-yellow-500/30 bg-yellow-500/10 p-4">
              <p className="text-sm text-yellow-200">
                Keep your API key secret. Never commit it to version control or
                expose it in client-side code.
              </p>
            </div>
          </div>
        )}

        {/* Step 2: Make first request */}
        {currentStep === 2 && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Send your first inference request. ASAHI will automatically route
              it to the cheapest model that meets your quality requirements:
            </p>
            <div className="relative">
              <pre className="overflow-x-auto rounded-md border border-border bg-background p-4 font-mono text-sm text-foreground">
                {codeSnippets[2]}
              </pre>
              <button
                onClick={() => copyToClipboard(codeSnippets[2])}
                className="absolute right-3 top-3 rounded-md border border-border p-1.5 text-muted-foreground hover:text-foreground transition-colors"
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
            </div>
            <p className="text-sm text-muted-foreground">
              Or try it in the{" "}
              <Link
                href={`/${params.orgSlug}/gateway/playground`}
                className="text-asahi hover:underline"
              >
                Playground
              </Link>{" "}
              without writing any code.
            </p>
          </div>
        )}

        {/* Step 3: Watch savings */}
        {currentStep === 3 && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Once you start sending requests, your savings will appear on the
              dashboard in real-time. ASAHI optimizes costs through:
            </p>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li className="flex items-center gap-2">
                <div className="h-1.5 w-1.5 rounded-full bg-green-400" />
                Smart routing to the cheapest model meeting your quality constraints
              </li>
              <li className="flex items-center gap-2">
                <div className="h-1.5 w-1.5 rounded-full bg-blue-400" />
                Multi-tier caching (exact, semantic, and intermediate)
              </li>
              <li className="flex items-center gap-2">
                <div className="h-1.5 w-1.5 rounded-full bg-purple-400" />
                Prompt optimization and token compression
              </li>
              <li className="flex items-center gap-2">
                <div className="h-1.5 w-1.5 rounded-full bg-yellow-400" />
                Request batching for throughput workloads
              </li>
            </ul>
            <Link
              href={`/${params.orgSlug}/dashboard`}
              className="inline-flex items-center gap-2 rounded-md bg-asahi px-4 py-2 text-sm font-medium text-white hover:bg-asahi-dark transition-colors"
            >
              Go to Dashboard
              <ChevronRight className="h-4 w-4" />
            </Link>
          </div>
        )}
      </div>

      {/* Navigation buttons */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setCurrentStep((s) => Math.max(0, s - 1))}
          disabled={currentStep === 0}
          className="rounded-md border border-border px-4 py-2 text-sm text-muted-foreground hover:text-foreground disabled:opacity-50 transition-colors"
        >
          Back
        </button>
        {currentStep < steps.length - 1 && (
          <button
            onClick={() => setCurrentStep((s) => s + 1)}
            className="inline-flex items-center gap-2 rounded-md bg-asahi px-4 py-2 text-sm font-medium text-white hover:bg-asahi-dark transition-colors"
          >
            Continue
            <ChevronRight className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
