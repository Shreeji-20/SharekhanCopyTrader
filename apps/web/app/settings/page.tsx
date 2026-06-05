"use client";

import { useQuery } from "@tanstack/react-query";
import { KeyRound, Power, ShieldCheck } from "lucide-react";
import { Page } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";

type TradingMode = {
  api_paper_trading_mode: boolean;
  copy_trading_dry_run: boolean;
  broker_router_paper_trading_mode: boolean | null;
  live_orders_enabled: boolean;
  broker_router_health: Record<string, unknown>;
};

export default function SettingsPage() {
  const {data: tradingMode, isLoading} = useQuery({
    queryKey: ["trading-mode"],
    queryFn: () => apiFetch<TradingMode>("/system/trading-mode"),
    refetchInterval: 5000
  });

  return (
    <Page title="Settings">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Security</CardTitle>
            <KeyRound className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="grid gap-3 text-sm">
            <div className="flex items-center justify-between rounded-md border p-3">
              <span className="text-muted-foreground">Credentials</span>
              <Badge>ENCRYPTED</Badge>
            </div>
            <div className="flex items-center justify-between rounded-md border p-3">
              <span className="text-muted-foreground">Broker router</span>
              <Badge>{tradingMode?.broker_router_health?.status === "ok" ? "CONNECTED" : "DEGRADED"}</Badge>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Order Mode</CardTitle>
            <Power className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="grid gap-3 text-sm">
            <div className="flex items-center justify-between rounded-md border p-3">
              <span className="text-muted-foreground">Live orders</span>
              <Badge>{tradingMode?.live_orders_enabled ? "LIVE" : isLoading ? "PENDING" : "PAPER"}</Badge>
            </div>
            <div className="grid gap-2 rounded-md border p-3">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">API paper mode</span>
                <span>{String(tradingMode?.api_paper_trading_mode ?? "-")}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Copy dry run</span>
                <span>{String(tradingMode?.copy_trading_dry_run ?? "-")}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Broker paper mode</span>
                <span>{String(tradingMode?.broker_router_paper_trading_mode ?? "-")}</span>
              </div>
            </div>
            <div className="flex items-center gap-2 rounded-md border p-3 text-muted-foreground">
              <ShieldCheck className="h-4 w-4 shrink-0" />
              <span>Server flags are read from the running API and broker-router processes.</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </Page>
  );
}
