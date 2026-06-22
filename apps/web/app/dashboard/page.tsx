"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Landmark, PlugZap, TrendingUp } from "lucide-react";
import { Page } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";

type Metrics = {
  active_copy_accounts: number;
  open_positions: number;
  total_pnl: string;
  broker_connection_status: "CONNECTED" | "DEGRADED" | "DISCONNECTED";
};

const emptyMetrics: Metrics = {
  active_copy_accounts: 0,
  open_positions: 0,
  total_pnl: "0",
  broker_connection_status: "DISCONNECTED"
};

export default function DashboardPage() {
  const {data = emptyMetrics, isLoading} = useQuery({
    queryKey: ["dashboard-metrics"],
    queryFn: () => apiFetch<Metrics>("/dashboard/metrics"),
    retry: false
  });
  const cards = [
    {label: "Copy Accounts", value: data.active_copy_accounts, icon: Landmark},
    {label: "Open Positions", value: data.open_positions, icon: Activity},
    {label: "Total P&L", value: `Rs ${Number(data.total_pnl).toLocaleString("en-IN")}`, icon: TrendingUp},
    {label: "Broker Status", value: data.broker_connection_status, icon: PlugZap}
  ];

  return (
    <Page title="Dashboard">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((item) => {
          const Icon = item.icon;
          return (
            <Card key={item.label}>
              <CardHeader>
                <CardTitle>{item.label}</CardTitle>
                <Icon className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                {item.label === "Broker Status" ? (
                  <Badge>{String(item.value)}</Badge>
                ) : (
                  <div className="text-2xl font-semibold">{isLoading ? "-" : item.value}</div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
      <div className="mt-4 rounded-lg border bg-card p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">Intraday Copy Flow</h2>
          <Badge>{data.broker_connection_status}</Badge>
        </div>
        <div className="grid h-80 place-items-center rounded-md border border-dashed text-sm text-muted-foreground">
          No intraday copy-flow events have been recorded yet.
        </div>
      </div>
    </Page>
  );
}
