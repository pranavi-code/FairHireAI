import { Link, useRouter } from "@tanstack/react-router";
import { LayoutDashboard, LineChart, LogOut, Menu, PlayCircle, ShieldCheck, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/assessment/new", label: "New assessment", icon: PlayCircle },
  { to: "/progress", label: "Progress", icon: LineChart },
  { to: "/settings/privacy", label: "Privacy", icon: ShieldCheck },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  async function handleSignOut() {
    await signOut();
    router.navigate({ to: "/" });
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Slim top bar — no dark full-height sidebar */}
      <header className="sticky top-0 z-30 border-b border-border/70 bg-card/85 backdrop-blur supports-[backdrop-filter]:bg-card/70">
        <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-4 px-4 sm:px-6">
          <Link to="/dashboard" className="flex items-center gap-2 shrink-0">
            <span className="grid h-8 w-8 place-items-center rounded-xl bg-[image:var(--gradient-primary)] text-primary-foreground shadow-elegant">
              <span className="text-sm font-black">F</span>
            </span>
            <span className="hidden text-sm font-semibold tracking-tight text-foreground sm:inline">
              FairHireAI
            </span>
          </Link>

          <nav className="ml-2 hidden md:block" aria-label="Primary">
            <ul className="flex items-center gap-1">
              {NAV.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground"
                    activeProps={{ className: "bg-primary/10 text-primary" }}
                  >
                    <item.icon className="h-4 w-4" aria-hidden />
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <span className="hidden max-w-[180px] truncate text-xs text-muted-foreground md:inline">
              {user?.email}
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="hidden md:inline-flex"
              onClick={handleSignOut}
            >
              <LogOut className="mr-1.5 h-4 w-4" aria-hidden />
              Sign out
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              aria-label="Toggle navigation"
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
            >
              {open ? (
                <X className="h-5 w-5" aria-hidden />
              ) : (
                <Menu className="h-5 w-5" aria-hidden />
              )}
            </Button>
          </div>
        </div>

        {open && (
          <nav className="border-t border-border bg-card px-3 py-2 md:hidden" aria-label="Mobile">
            <ul className="space-y-1">
              {NAV.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    onClick={() => setOpen(false)}
                    className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-foreground hover:bg-muted"
                    activeProps={{ className: "bg-primary/10 text-primary" }}
                  >
                    <item.icon className="h-4 w-4" aria-hidden />
                    {item.label}
                  </Link>
                </li>
              ))}
              <li>
                <button
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium text-foreground hover:bg-muted"
                  onClick={handleSignOut}
                >
                  <LogOut className="h-4 w-4" aria-hidden />
                  Sign out
                </button>
              </li>
            </ul>
          </nav>
        )}
      </header>

      <main id="main" className="min-w-0 flex-1">
        {children}
      </main>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <div className="relative overflow-hidden border-b border-border/70 bg-card">
      <div className="absolute inset-0 bg-aurora opacity-60" aria-hidden />
      <div className="relative mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 sm:py-10">
        <div
          className={cn(
            "flex flex-col gap-4",
            actions && "sm:flex-row sm:items-end sm:justify-between",
          )}
        >
          <div className="min-w-0">
            {eyebrow && (
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-evidence">
                {eyebrow}
              </div>
            )}
            <h1 className="text-3xl font-black tracking-tight text-foreground sm:text-4xl">
              {title}
            </h1>
            {description && (
              <p className="mt-2 max-w-2xl text-sm text-muted-foreground sm:text-base">
                {description}
              </p>
            )}
          </div>
          {actions && <div className="flex flex-wrap gap-2 shrink-0">{actions}</div>}
        </div>
      </div>
    </div>
  );
}

export function PageBody({ children }: { children: ReactNode }) {
  return <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6">{children}</div>;
}
