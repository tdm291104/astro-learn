import { AuthGuard } from "@/components/common/AuthGuard";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { Navbar } from "@/components/common/Navbar";
import { Sidebar } from "@/components/common/Sidebar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Navbar />
          <ErrorBoundary>
            <main className="flex-1">
              <div className="app-container py-6 sm:py-8 lg:py-10">
                {children}
              </div>
            </main>
          </ErrorBoundary>
        </div>
      </div>
    </AuthGuard>
  );
}
