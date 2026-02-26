import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <SignIn
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
