import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full border border-[#FF6B35]/30 bg-[#FF6B35]/10">
          <span className="text-2xl font-bold text-[#FF6B35]">404</span>
        </div>
        <h2 className="mb-2 text-lg font-semibold text-foreground">
          Page not found
        </h2>
        <p className="mb-6 text-sm text-muted-foreground">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <Link
          href="/"
          className="inline-block rounded-lg bg-[#FF6B35] px-6 py-2 text-sm font-medium text-white hover:bg-[#E55A24] transition-colors"
        >
          Return Home
        </Link>
      </div>
    </div>
  );
}
