import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { SignIn } from "@clerk/nextjs";
import { dark } from "@clerk/themes";

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
          baseTheme: dark,
          variables: {
            colorPrimary: "#FF6B35",
            colorBackground: "#121212",
            colorInputBackground: "#1a1a1a",
            colorInputText: "#f5f5f5",
            colorText: "#f5f5f5",
            colorTextSecondary: "#a3a3a3",
            colorNeutral: "#f5f5f5",
          },
          elements: {
            rootBox: "mx-auto",
            card: "bg-[#121212] border border-[#2a2a2a] shadow-lg",
            headerTitle: "text-white",
            headerSubtitle: "text-neutral-400",
            formButtonPrimary:
              "bg-[#FF6B35] hover:bg-[#E55A24] text-white",
            formFieldInput:
              "bg-[#1a1a1a] border-[#2a2a2a] text-white placeholder:text-neutral-500",
            formFieldLabel: "text-neutral-300",
            otpCodeFieldInput:
              "bg-[#1a1a1a] border-[#2a2a2a] text-white !text-white",
            footerActionLink: "text-[#FF6B35] hover:text-[#FFB84D]",
            socialButtonsBlockButton:
              "bg-[#1a1a1a] border-[#2a2a2a] text-white hover:bg-[#222]",
            socialButtonsBlockButtonText: "text-white",
            dividerLine: "bg-[#2a2a2a]",
            dividerText: "text-neutral-500",
            identityPreview: "bg-[#1a1a1a] border-[#2a2a2a]",
            identityPreviewText: "text-white",
            identityPreviewEditButton: "text-[#FF6B35]",
            formFieldAction: "text-[#FF6B35]",
            formResendCodeLink: "text-[#FF6B35]",
            alternativeMethodsBlockButton:
              "bg-[#1a1a1a] border-[#2a2a2a] text-white hover:bg-[#222]",
            backLink: "text-[#FF6B35]",
          },
        }}
      />
    </div>
  );
}
