import { createFileRoute, Outlet, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { AppShell } from "@/components/app/AppShell";
import { LoadingState } from "@/components/app/StateViews";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/_authenticated")({
  ssr: false, // Supabase session lives in localStorage; gate client-side only.
  component: AuthenticatedLayout,
});

function AuthenticatedLayout() {
  const { ready, user, configured } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!ready) return;
    if (!configured || !user) {
      navigate({ to: "/auth", replace: true });
    }
  }, [ready, user, configured, navigate]);

  if (!ready || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingState label="Restoring your session…" />
      </div>
    );
  }

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
