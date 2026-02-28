import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { SignUp } from "@clerk/nextjs";

export default async function SignUpPage() {
  // If the user is already authenticated, send them straight to bootstrap.
  const { userId } = await auth();
  if (userId) {
    redirect("/bootstrap");
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <SignUp
        path="/sign-up"
        routing="path"
        signInUrl="/sign-in"
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
