import { auth, currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { BootstrapError } from "./error-ui";

type LoginResponse = {
  user_id: string;
  email: string;
  name: string | null;
  organisations: Array<{
    org_id: string;
    org_slug: string;
    org_name: string;
    role: string;
    plan: string;
  }>;
};

type SignupResponse = {
  user_id: string;
  email: string;
  org_id: string;
  org_slug: string;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default async function BootstrapPage() {
  const { userId } = await auth();
  if (!userId) {
    redirect("/sign-in");
  }

  const user = await currentUser();
  const primaryEmail =
    user?.emailAddresses[0]?.emailAddress ?? undefined;
  const fullName = user?.fullName ?? undefined;

  if (!primaryEmail) {
    redirect("/sign-in");
  }

  // 1. Try login by Clerk user ID
  let loginRes: Response;
  try {
    loginRes = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clerk_user_id: userId }),
      cache: "no-store",
    });
  } catch {
    // Backend is unreachable (not running, network error, etc.)
    return (
      <BootstrapError message="Cannot connect to the ASAHI backend. Make sure the backend server is running." />
    );
  }

  if (loginRes.ok) {
    const data = (await loginRes.json()) as LoginResponse;
    const firstOrg = data.organisations[0];
    if (firstOrg) {
      redirect(`/${firstOrg.org_slug}/dashboard`);
    }
    // User exists but has no organisations — fall through to create one
  } else if (loginRes.status !== 404) {
    const detail = await loginRes.text().catch(() => "Unknown error");
    return (
      <BootstrapError message={`Login failed (${loginRes.status}): ${detail}`} />
    );
  }

  // 2. If login 404, this is a new user — call signup to create user + org
  let signupRes: Response;
  try {
    signupRes = await fetch(`${API_BASE}/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: primaryEmail,
        name: fullName,
        clerk_user_id: userId,
        org_name: fullName ? `${fullName}'s Org` : undefined,
      }),
      cache: "no-store",
    });
  } catch {
    return (
      <BootstrapError message="Cannot connect to the ASAHI backend. Make sure the backend server is running." />
    );
  }

  if (!signupRes.ok) {
    const detail = await signupRes.text().catch(() => "Unknown error");
    return (
      <BootstrapError message={`Account setup failed (${signupRes.status}): ${detail}`} />
    );
  }

  const created = (await signupRes.json()) as SignupResponse;
  redirect(`/${created.org_slug}/dashboard`);
}
