"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronRight, Copy, Key, Package, TrendingDown, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { getAnalyticsOverview } from "@/lib/api";
import { fireConfetti } from "@/lib/confetti";

const steps = [
  {
    title: "Install the SDK",
    description: "Add the ASAHIO Python SDK to your project.",
    icon: Package,
  },
  {
    title: "Create an API key",
    description: "Issue an org-scoped key for the gateway and SDK.",
    icon: Key,
  },
  {
    title: "Send a request",
    description: "Use the canonical ASAHIO contract with AUTO routing.",
    icon: Zap,
  },
  {
    title: "Track savings",
    description: "Verify cost, cache, and routing data in the dashboard.",
    icon: TrendingDown,
  },
] as const;

const codeSnippets: Record<number, string> = {
  0: `pip install asahio-ai`,
  1: `from asahio import Asahio

client = Asahio(
    api_key="asahio_live_your_key_here",
    org_slug="your-org-slug",
)`,
  2: `response = client.chat.completions.create(
    messages=[
        {"role": "user", "content": "Summarize the incident timeline."}
    ],
    routing_mode="AUTO",
    intervention_mode="OBSERVE",
)

print(response.choices[0].message.content)
print(response.asahio.model_used)
print(f"Saved: \${response.asahio.savings_usd:.4f}")`,
};

export default function OnboardingPage() {
  const params = useParams();
  const orgSlug = typeof params?.orgSlug === "string" ? params.orgSlug : "";
  const [currentStep, setCurrentStep] = useState(0);
  const prevRequests = useRef<number | null>(null);
  const confettiFired = useRef(false);

  const { data: overview } = useQuery({
    queryKey: ["overview", orgSlug, "onboarding"],
    queryFn: () => getAnalyticsOverview("30d", undefined, orgSlug),
    refetchInterval: 5_000,
  });

  useEffect(() => {
    if (!overview || confettiFired.current) return;
    const total = overview.total_requests;
    if (prevRequests.current !== null && prevRequests.current === 0 && total > 0) {
      confettiFired.current = true;
      fireConfetti();
      toast.success("Your first request completed. ASAHIO is now tracking savings.");
    }
    prevRequests.current = total;
  }, [overview]);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success("Copied to clipboard");
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Getting Started</h1>
          <p className="text-sm text-muted-foreground">Set up ASAHIO in a few deliberate steps.</p>
        </div>
        <Link
          href={`/${orgSlug}/dashboard`}
          className="text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          Skip setup
        </Link>
      </div>

      <div className="flex items-center gap-2">
        {steps.map((step, index) => (
          <div key={step.title} className="flex items-center gap-2">
            <button
              onClick={() => setCurrentStep(index)}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium transition-colors",
                index < currentStep
                  ? "bg-green-500 text-white"
                  : index === currentStep
                    ? "bg-asahio text-white"
                    : "border border-border bg-background text-muted-foreground"
              )}
            >
              {index < currentStep ? <Check className="h-4 w-4" /> : index + 1}
            </button>
            {index < steps.length - 1 && (
              <div className={cn("h-0.5 w-8 sm:w-16", index < currentStep ? "bg-green-500" : "bg-border")} />
            )}
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-border bg-card p-6 sm:p-8 shadow-sm max-h-[calc(100vh-280px)] overflow-y-auto">
        <div className="mb-6 flex items-center gap-3">
          {(() => {
            const Icon = steps[currentStep].icon;
            return (
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-asahio/20">
                <Icon className="h-5 w-5 text-asahio" />
              </div>
            );
          })()}
          <div>
            <h2 className="text-lg font-semibold text-foreground">{steps[currentStep].title}</h2>
            <p className="text-sm text-muted-foreground">{steps[currentStep].description}</p>
          </div>
        </div>

        {currentStep === 0 && (
          <StepBlock
            text="Install the SDK from the repo or your internal package registry."
            code={codeSnippets[0]}
            onCopy={copyToClipboard}
          />
        )}

        {currentStep === 1 && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Create a key from the <Link href={`/${orgSlug}/keys`} className="text-asahio hover:underline">API Keys page</Link>, then initialize the client with your org slug.
            </p>
            <CodeBlock code={codeSnippets[1]} onCopy={copyToClipboard} />
            <div className="rounded-md border border-yellow-500/30 bg-yellow-500/10 p-4 text-sm text-yellow-200">
              Store the raw key once, then rotate it if exposure is suspected. ASAHIO only returns the full value at creation time.
            </div>
          </div>
        )}

        {currentStep === 2 && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Send your first request through the canonical gateway shape. AUTO routing keeps the public API stable while the backend decides model selection.
            </p>
            <CodeBlock code={codeSnippets[2]} onCopy={copyToClipboard} />
            <p className="text-sm text-muted-foreground">
              If you want a quick manual check first, use the <Link href={`/${orgSlug}/gateway/playground`} className="text-asahio hover:underline">Playground</Link>.
            </p>
          </div>
        )}

        {currentStep === 3 && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Once traffic starts flowing, ASAHIO reports savings, cache hit rate, and routing decisions back into the dashboard.
            </p>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li className="flex items-center gap-2"><div className="h-1.5 w-1.5 rounded-full bg-green-400" /> Savings and request trends in the dashboard header and analytics.</li>
              <li className="flex items-center gap-2"><div className="h-1.5 w-1.5 rounded-full bg-blue-400" /> Billing usage bars and invoice history on the billing page.</li>
              <li className="flex items-center gap-2"><div className="h-1.5 w-1.5 rounded-full bg-asahio" /> Routing metadata in the playground and audit surfaces.</li>
            </ul>
            <Link
              href={`/${orgSlug}/dashboard`}
              className="inline-flex items-center gap-2 rounded-md bg-asahio px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-asahio-dark"
            >
              Open Dashboard
              <ChevronRight className="h-4 w-4" />
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

function StepBlock({ text, code, onCopy }: { text: string; code: string; onCopy: (text: string) => void }) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{text}</p>
      <CodeBlock code={code} onCopy={onCopy} />
    </div>
  );
}

function CodeBlock({ code, onCopy }: { code: string; onCopy: (text: string) => void }) {
  return (
    <div className="relative">
      <pre className="overflow-x-auto rounded-md border border-border bg-background p-4 font-mono text-sm text-foreground">
        {code}
      </pre>
      <button
        onClick={() => onCopy(code)}
        className="absolute right-3 top-3 rounded-md border border-border p-1.5 text-muted-foreground transition-colors hover:text-foreground"
      >
        <Copy className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}



