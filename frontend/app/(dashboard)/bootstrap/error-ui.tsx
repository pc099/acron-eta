"use client";

import { useClerk } from "@clerk/nextjs";
import { useRouter } from "next/navigation";

export function BootstrapError({ message }: { message: string }) {
  const { signOut } = useClerk();
  const router = useRouter();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-red-500/30 bg-red-500/10">
          <span className="text-lg text-red-500">!</span>
        </div>
        <h2 className="mb-2 text-lg font-semibold text-foreground">
          Connection Error
        </h2>
        <p className="mb-6 text-sm text-muted-foreground">{message}</p>
        <div className="flex flex-col gap-3">
          <button
            onClick={() => router.refresh()}
            className="rounded-lg bg-asahi px-4 py-2 text-sm font-medium text-white hover:bg-asahi-dark transition-colors"
          >
            Retry
          </button>
          <button
            onClick={() => signOut({ redirectUrl: "/" })}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            Sign Out &amp; Return Home
          </button>
        </div>
      </div>
    </div>
  );
}
