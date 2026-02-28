import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { SignIn } from "@clerk/nextjs";

export default async function SignInPage() {
  // If the user is already authenticated, send them straight to bootstrap.
  // This avoids Clerk's forceRedirectUrl firing on every render and creating
  // a silent loop when the backend is down.
  const { userId } = await auth();
  if (userId) {
    redirect("/bootstrap");
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <SignIn
        path="/sign-in"
        routing="path"
        signUpUrl="/sign-up"
        forceRedirectUrl="/bootstrap"
        appearance={{
          elements: {
            rootBox: "mx-auto",
            card: "bg-card border border-border shadow-lg",
            headerTitle: "text-foreground",
            headerSubtitle: "text-muted-foreground",
            formButtonPrimary:
              "bg-asahi hover:bg-asahi-dark text-white",
          },
        }}
      />
    </div>
  );
}
