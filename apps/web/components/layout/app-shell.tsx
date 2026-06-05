"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import {
  Activity,
  BarChart3,
  BookOpen,
  BriefcaseBusiness,
  ClipboardList,
  Copy,
  FileClock,
  Home,
  Landmark,
  LogOut,
  Moon,
  PanelLeft,
  Plus,
  RadioTower,
  Settings,
  ShieldCheck,
  Sun,
  Users
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ApiError, apiFetch, clearAccessToken, getAccessToken } from "@/lib/api";
import { cn } from "@/lib/utils";

const navigation = [
  {href: "/dashboard", label: "Dashboard", icon: Home},
  {href: "/accounts", label: "Accounts", icon: Landmark},
  {href: "/accounts/new", label: "New Account", icon: Plus},
  {href: "/copy-groups", label: "Copy Groups", icon: Users},
  {href: "/live-copy", label: "Live Copy", icon: RadioTower},
  {href: "/orders/master", label: "Master Orders", icon: ClipboardList},
  {href: "/orders/copy", label: "Copy Orders", icon: Copy},
  {href: "/positions", label: "Positions", icon: BriefcaseBusiness},
  {href: "/holdings", label: "Holdings", icon: BookOpen},
  {href: "/trades", label: "Trades", icon: Activity},
  {href: "/risk-settings", label: "Risk Settings", icon: ShieldCheck},
  {href: "/settings", label: "Settings", icon: Settings},
  {href: "/logs", label: "Logs", icon: FileClock}
];

type TradingMode = {
  live_orders_enabled: boolean;
  broker_router_health?: {status?: string};
};

let verifiedToken: string | null = null;

export function AppShell({children}: {children: ReactNode}) {
  const pathname = usePathname();
  const {theme, setTheme} = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [authMessage, setAuthMessage] = useState("Checking session...");
  const {data: tradingMode} = useQuery({
    queryKey: ["trading-mode-header"],
    queryFn: () => apiFetch<TradingMode>("/system/trading-mode"),
    enabled: authChecked,
    refetchInterval: 5000,
    retry: false
  });

  useEffect(() => {
    let active = true;

    function redirectToLogin() {
      if (!active) return;
      setAuthMessage("Redirecting to sign in...");
      setAuthChecked(false);
      window.setTimeout(() => {
        if (window.location.pathname !== "/login") window.location.replace("/login");
      }, 0);
    }

    async function verifySession() {
      const token = getAccessToken();
      if (!token) {
        verifiedToken = null;
        redirectToLogin();
        return;
      }
      if (verifiedToken === token) {
        setAuthChecked(true);
        return;
      }
      try {
        await apiFetch("/auth/me", {timeoutMs: 10_000});
        verifiedToken = token;
        if (active) setAuthChecked(true);
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          verifiedToken = null;
          clearAccessToken();
          toast.error("Please sign in before continuing.");
          redirectToLogin();
          return;
        }
        if (error instanceof ApiError && error.status === 408) {
          toast.error("Session check timed out. Please try signing in again.");
          verifiedToken = null;
          clearAccessToken();
          redirectToLogin();
          return;
        }
        if (active) setAuthChecked(true);
      }
    }

    void verifySession();
    return () => {
      active = false;
    };
  }, []);

  function logout() {
    verifiedToken = null;
    clearAccessToken();
    window.location.replace("/login");
  }

  if (!authChecked) {
    return (
      <main className="grid min-h-screen place-items-center bg-background p-4 text-sm text-muted-foreground">
        {authMessage}
      </main>
    );
  }

  const navItems = (
    <nav className="grid gap-1 p-3">
      {navigation.map((item) => {
        const Icon = item.icon;
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setMobileOpen(false)}
            className={cn(
              "flex h-9 items-center gap-2 rounded-md px-3 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
              active && "bg-muted text-foreground"
            )}
          >
            <Icon className="h-4 w-4" />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-64 shrink-0 border-r bg-card lg:block">
        <div className="flex h-14 items-center gap-2 border-b px-4">
          <BarChart3 className="h-5 w-5 text-primary" />
          <span className="text-sm font-semibold">Copy Trading</span>
        </div>
        {navItems}
      </aside>
      {mobileOpen ? (
        <div className="fixed inset-0 z-40 bg-black/30 lg:hidden" onClick={() => setMobileOpen(false)}>
          <aside className="h-full w-72 border-r bg-card" onClick={(event) => event.stopPropagation()}>
            <div className="flex h-14 items-center gap-2 border-b px-4">
              <BarChart3 className="h-5 w-5 text-primary" />
              <span className="text-sm font-semibold">Copy Trading</span>
            </div>
            {navItems}
          </aside>
        </div>
      ) : null}
      <main className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b bg-background/95 px-4 backdrop-blur">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              title="Navigation"
              aria-label="Navigation"
              className="lg:hidden"
              onClick={() => setMobileOpen(true)}
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
            <div className="hidden items-center gap-2 sm:flex">
              <Badge>{!tradingMode ? "PENDING" : tradingMode.broker_router_health?.status === "ok" ? "CONNECTED" : "DEGRADED"}</Badge>
              <span className="text-sm text-muted-foreground">
                {tradingMode?.live_orders_enabled ? "Live trading" : "Paper trading"}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              title="Toggle theme"
              aria-label="Toggle theme"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            >
              <Sun className="h-4 w-4 dark:hidden" />
              <Moon className="hidden h-4 w-4 dark:block" />
            </Button>
            <Button variant="outline" size="icon" title="Sign out" aria-label="Sign out" onClick={logout}>
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>
        <div className="mx-auto w-full max-w-7xl p-4 sm:p-6">{children}</div>
      </main>
    </div>
  );
}
