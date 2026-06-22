"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Download, KeyRound, Loader2, Power, ShieldCheck, Upload, Users } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Page } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";

type TradingMode = {
  api_paper_trading_mode: boolean;
  copy_trading_dry_run: boolean;
  broker_router_paper_trading_mode: boolean | null;
  live_orders_enabled: boolean;
  broker_router_health: Record<string, unknown>;
};

type CurrentUser = {
  id: string;
  email: string;
  role: "ADMIN" | "USER";
  is_active: boolean;
};

type UserArchive = {
  format: "sharekhan-copy-trader.users";
  version: 1;
  exported_at: string;
  users: Array<Record<string, unknown>>;
};

type UserImportResult = {
  total: number;
  created: number;
  updated: number;
  unchanged: number;
};

export default function SettingsPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [importResult, setImportResult] = useState<UserImportResult | null>(null);
  const {data: tradingMode, isLoading} = useQuery({
    queryKey: ["trading-mode"],
    queryFn: () => apiFetch<TradingMode>("/system/trading-mode"),
    refetchInterval: 5000
  });
  const {data: currentUser} = useQuery({
    queryKey: ["current-user"],
    queryFn: () => apiFetch<CurrentUser>("/auth/me")
  });

  async function exportUsers() {
    setIsExporting(true);
    try {
      const archive = await apiFetch<UserArchive>("/users/export");
      const blob = new Blob([JSON.stringify(archive, null, 2)], {type: "application/json"});
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      const timestamp = archive.exported_at.replace(/[-:]/g, "").replace(/\.\d+/, "");
      link.href = url;
      link.download = `sharekhan-copy-trader-users-${timestamp}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success(`Exported ${archive.users.length} users.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not export users.");
    } finally {
      setIsExporting(false);
    }
  }

  function chooseArchive(file: File | null) {
    setImportResult(null);
    if (!file) {
      setSelectedFile(null);
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      toast.error("User archive must be 10 MB or smaller.");
      setSelectedFile(null);
      return;
    }
    setSelectedFile(file);
  }

  async function importUsers() {
    if (!selectedFile) return;
    const confirmed = window.confirm(
      "Import every user field from this archive? Existing users with matching IDs will be updated, including password hashes, roles, active state, and timestamps."
    );
    if (!confirmed) return;

    setIsImporting(true);
    try {
      const text = await selectedFile.text();
      const archive = JSON.parse(text) as unknown;
      const result = await apiFetch<UserImportResult>("/users/import", {
        method: "POST",
        body: JSON.stringify(archive)
      });
      setImportResult(result);
      toast.success(`Imported ${result.total} users.`);
    } catch (error) {
      const message = error instanceof SyntaxError
        ? "The selected file is not valid JSON."
        : error instanceof Error
          ? error.message
          : "Could not import users.";
      toast.error(message);
    } finally {
      setIsImporting(false);
    }
  }

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

        {currentUser?.role === "ADMIN" ? (
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>User Archive</CardTitle>
              <div className="flex items-center gap-2">
                <Badge>ADMIN</Badge>
                <Users className="h-4 w-4 text-muted-foreground" />
              </div>
            </CardHeader>
            <CardContent className="grid gap-4">
              <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                <div className="grid gap-2 text-sm">
                  <div className="flex items-center justify-between gap-3 rounded-md border p-3">
                    <span className="text-muted-foreground">Archive scope</span>
                    <span className="text-right">All user fields</span>
                  </div>
                  <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>The JSON contains password hashes, roles, status, IDs, and timestamps. Store it securely.</span>
                  </div>
                </div>
                <Button variant="outline" onClick={() => void exportUsers()} disabled={isExporting || isImporting}>
                  {isExporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                  {isExporting ? "Exporting" : "Export Users"}
                </Button>
              </div>

              <div className="grid gap-3 border-t pt-4 md:grid-cols-[minmax(0,1fr)_auto_auto] md:items-center">
                <div className="min-w-0 rounded-md border px-3 py-2 text-sm">
                  <div className="truncate font-medium">{selectedFile?.name ?? "No archive selected"}</div>
                  <div className="text-xs text-muted-foreground">
                    {selectedFile ? `${Math.max(1, Math.ceil(selectedFile.size / 1024))} KB` : "JSON archive, maximum 10 MB"}
                  </div>
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/json,.json"
                  className="hidden"
                  onChange={(event) => {
                    chooseArchive(event.target.files?.[0] ?? null);
                    event.target.value = "";
                  }}
                />
                <Button variant="outline" onClick={() => fileInputRef.current?.click()} disabled={isExporting || isImporting}>
                  <Upload className="h-4 w-4" />
                  Choose Archive
                </Button>
                <Button onClick={() => void importUsers()} disabled={!selectedFile || isExporting || isImporting}>
                  {isImporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                  {isImporting ? "Importing" : "Import Users"}
                </Button>
              </div>

              {importResult ? (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {([
                    ["Total", importResult.total],
                    ["Created", importResult.created],
                    ["Updated", importResult.updated],
                    ["Unchanged", importResult.unchanged]
                  ] as const).map(([label, count]) => (
                    <div key={label} className="rounded-md border p-3 text-center">
                      <div className="text-lg font-semibold">{count}</div>
                      <div className="text-xs text-muted-foreground">{label}</div>
                    </div>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>
        ) : null}
      </div>
    </Page>
  );
}
