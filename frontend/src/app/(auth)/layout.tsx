export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden p-4">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            "radial-gradient(circle at 30% 20%, rgba(226,201,126,0.08), transparent 45%), radial-gradient(circle at 75% 80%, rgba(79,195,247,0.08), transparent 45%)",
        }}
      />
      <div className="w-full max-w-md">{children}</div>
    </div>
  );
}
