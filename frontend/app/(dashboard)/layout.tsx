export default function DashboardRootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Authentication is enforced by Clerk middleware; this layout only renders children.
  return <>{children}</>;
}
