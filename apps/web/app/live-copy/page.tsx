"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Pause, Play, RadioTower, RotateCcw, ShieldCheck, Square, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Page } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";

type Account = {
  id: string;
  account_name: string;
  account_type: "MASTER" | "COPY";
  customer_id: string | null;
  access_token: string | null;
  is_active: boolean;
};

type CopyGroup = {
  id: string;
  name: string;
  master_account_id: string;
  is_active: boolean;
};

type CopySession = {
  id: string;
  master_account_id: string;
  status: "RUNNING" | "PAUSED" | "STOPPED" | "ERROR";
  active_group_ids: string[];
  dry_run: boolean;
  started_at: string;
  stopped_at: string | null;
  last_error: string | null;
};

type ValidationResult = {
  ok: boolean;
  warnings: string[];
  duplicate_copy_accounts: {copy_account_id: string; account_name: string; copy_group_ids: string[]}[];
  copy_account_count: number;
};

type MasterTradeEvent = {
  id: string;
  symbol: string;
  exchange: string;
  side: string;
  quantity: number;
  price: string;
  copied_status: string;
  external_order_id: string | null;
  external_trade_id: string | null;
  created_at: string;
};

type CopiedTradeOrder = {
  id: string;
  master_trade_event_id: string;
  copy_group_id: string;
  copier_account_id: string;
  child_order_id: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
};

type TradingMode = {
  api_paper_trading_mode: boolean;
  copy_trading_dry_run: boolean;
  broker_router_paper_trading_mode: boolean | null;
  live_orders_enabled: boolean;
};

type StreamStatus = {
  status: string;
  task_state?: string;
  is_connected: boolean;
  module_ready: boolean;
  ack_subscription_sent: boolean;
  customer_id_present?: boolean;
  proxy_configured?: boolean;
  last_message_at?: string | null;
  last_error?: string | null;
  messages_received?: number;
  ack_messages_received?: number;
  feed_messages_received?: number;
  raw_messages_received?: number;
  last_sent_payload?: Record<string, unknown> | null;
  sent_payloads?: {type: string; sent_at: string; payload: Record<string, unknown>}[];
  recent_messages?: {type: string; received_at: string; payload: unknown}[];
};

function diagnosticKey(kind: string, type: string, timestamp: string, payload: unknown) {
  const payloadText = (() => {
    try {
      return JSON.stringify(payload);
    } catch {
      return String(payload);
    }
  })();
  return `${kind}-${type}-${timestamp}-${payloadText.slice(0, 120)}`;
}

export default function LiveCopyPage() {
  const queryClient = useQueryClient();
  const [masterAccountId, setMasterAccountId] = useState("");
  const [selectedGroupIds, setSelectedGroupIds] = useState<string[]>([]);
  const [dryRun, setDryRun] = useState(true);
  const [dryRunTouched, setDryRunTouched] = useState(false);
  const [allowDuplicates, setAllowDuplicates] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState("");

  const {data: accounts = []} = useQuery({
    queryKey: ["accounts"],
    queryFn: () => apiFetch<Account[]>("/accounts")
  });
  const {data: groups = []} = useQuery({
    queryKey: ["copy-groups"],
    queryFn: () => apiFetch<CopyGroup[]>("/copy-groups")
  });
  const {data: sessions = []} = useQuery({
    queryKey: ["copy-sessions"],
    queryFn: () => apiFetch<CopySession[]>("/copy-sessions"),
    refetchInterval: 3000
  });
  const {data: tradingMode} = useQuery({
    queryKey: ["trading-mode"],
    queryFn: () => apiFetch<TradingMode>("/system/trading-mode"),
    refetchInterval: 5000
  });

  const masterAccounts = useMemo(() => accounts.filter((account) => account.account_type === "MASTER"), [accounts]);
  const accountNames = useMemo(() => new Map(accounts.map((account) => [account.id, account.account_name])), [accounts]);
  const filteredGroups = useMemo(
    () => groups.filter((group) => group.master_account_id === masterAccountId && group.is_active),
    [groups, masterAccountId]
  );
  const activeSession = sessions.find((session) => session.id === selectedSessionId) ?? sessions[0];

  const {data: events = []} = useQuery({
    queryKey: ["copy-session-events", activeSession?.id],
    enabled: Boolean(activeSession),
    queryFn: () => apiFetch<MasterTradeEvent[]>(`/copy-sessions/${activeSession?.id}/events`),
    refetchInterval: activeSession?.status === "RUNNING" ? 3000 : false
  });
  const {data: copiedOrders = []} = useQuery({
    queryKey: ["copy-session-copied-orders", activeSession?.id],
    enabled: Boolean(activeSession),
    queryFn: () => apiFetch<CopiedTradeOrder[]>(`/copy-sessions/${activeSession?.id}/copied-orders`),
    refetchInterval: activeSession?.status === "RUNNING" ? 3000 : false
  });
  const {data: streamStatus} = useQuery({
    queryKey: ["copy-session-stream-status", activeSession?.id],
    enabled: Boolean(activeSession),
    queryFn: () => apiFetch<StreamStatus>(`/copy-sessions/${activeSession?.id}/stream-status`),
    refetchInterval: activeSession?.status === "RUNNING" ? 2000 : 5000
  });

  useEffect(() => {
    if (!tradingMode || dryRunTouched) return;
    setDryRun(!tradingMode.live_orders_enabled);
  }, [dryRunTouched, tradingMode]);

  const startSession = useMutation({
    mutationFn: async () => {
      if (!masterAccountId || !selectedGroupIds.length) {
        throw new Error("Select a master account and at least one copy group.");
      }
      const validation = await apiFetch<ValidationResult>("/copy-groups/validate", {
        method: "POST",
        body: JSON.stringify({master_account_id: masterAccountId, copy_group_ids: selectedGroupIds})
      });
      setWarnings(validation.warnings);
      if (validation.duplicate_copy_accounts.length && !allowDuplicates) {
        throw new Error("A copy account is present in multiple selected groups.");
      }
      if (!dryRun && tradingMode && !tradingMode.live_orders_enabled) {
        throw new Error("Live order mode is blocked by server safety flags.");
      }
      return apiFetch<CopySession>("/copy-sessions/start", {
        method: "POST",
        body: JSON.stringify({
          master_account_id: masterAccountId,
          copy_group_ids: selectedGroupIds,
          dry_run: dryRun,
          allow_duplicate_copiers: allowDuplicates
        })
      });
    },
    onSuccess: (session) => {
      toast.success(session.dry_run ? "Dry-run copy session started." : "Live copy session started.");
      setSelectedSessionId(session.id);
      void queryClient.invalidateQueries({queryKey: ["copy-sessions"]});
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not start copy session.")
  });

  const controlSession = useMutation({
    mutationFn: ({sessionId, action}: {sessionId: string; action: "pause" | "resume" | "stop"}) =>
      apiFetch<CopySession>(`/copy-sessions/${sessionId}/${action}`, {method: "POST"}),
    onSuccess: (session) => {
      toast.success(`Session ${session.status.toLowerCase()}.`);
      setSelectedSessionId(session.id);
      void queryClient.invalidateQueries({queryKey: ["copy-sessions"]});
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not update session.")
  });

  const deleteSession = useMutation({
    mutationFn: (sessionId: string) => apiFetch<void>(`/copy-sessions/${sessionId}`, {method: "DELETE"}),
    onSuccess: () => {
      toast.success("Copy session deleted.");
      setSelectedSessionId("");
      void queryClient.invalidateQueries({queryKey: ["copy-sessions"]});
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not delete session.")
  });

  function toggleGroup(groupId: string) {
    setSelectedGroupIds((current) =>
      current.includes(groupId) ? current.filter((id) => id !== groupId) : [...current, groupId]
    );
  }

  const sentMessages = streamStatus?.sent_payloads?.slice(-4).reverse() ?? [];
  const recentMessages = streamStatus?.recent_messages?.slice(-5).reverse() ?? [];

  return (
    <Page title="Live Copy Trading">
      <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(320px,380px)_minmax(0,1fr)]">
        <div className="grid min-w-0 content-start gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Start Session</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3">
              <select
                value={masterAccountId}
                onChange={(event) => {
                  setMasterAccountId(event.target.value);
                  setSelectedGroupIds([]);
                  setWarnings([]);
                }}
                className="h-9 w-full min-w-0 rounded-md border bg-background px-3 text-sm"
              >
                <option value="">Select master account</option>
                {masterAccounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.account_name}
                  </option>
                ))}
              </select>
              <div className="grid max-h-56 min-w-0 gap-2 overflow-auto rounded-md border p-3">
                {filteredGroups.length ? (
                  filteredGroups.map((group) => (
                    <label key={group.id} className="flex min-w-0 items-center justify-between gap-3 text-sm">
                      <span className="min-w-0 truncate">{group.name}</span>
                      <input
                        className="shrink-0"
                        type="checkbox"
                        checked={selectedGroupIds.includes(group.id)}
                        onChange={() => toggleGroup(group.id)}
                      />
                    </label>
                  ))
                ) : (
                  <div className="text-sm text-muted-foreground">No active copy groups for this master.</div>
                )}
              </div>
              <label className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
                <span>Dry run mode</span>
                <input
                  type="checkbox"
                  checked={dryRun}
                  onChange={(event) => {
                    setDryRunTouched(true);
                    setDryRun(event.target.checked);
                  }}
                />
              </label>
              <div className="grid gap-2 rounded-md border p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Server mode</span>
                  <Badge>{tradingMode?.live_orders_enabled ? "LIVE" : "PAPER"}</Badge>
                </div>
                <div className="grid gap-1 text-xs text-muted-foreground">
                  <span>API paper: {String(tradingMode?.api_paper_trading_mode ?? "-")}</span>
                  <span>Copy dry run: {String(tradingMode?.copy_trading_dry_run ?? "-")}</span>
                  <span>Broker paper: {String(tradingMode?.broker_router_paper_trading_mode ?? "-")}</span>
                </div>
              </div>
              <label className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
                <span>Allow duplicate copiers</span>
                <input
                  type="checkbox"
                  checked={allowDuplicates}
                  onChange={(event) => setAllowDuplicates(event.target.checked)}
                />
              </label>
              <Button onClick={() => startSession.mutate()} disabled={startSession.isPending}>
                <Play className="h-4 w-4" />
                Start Copying
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Session Controls</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3">
              <select
                value={activeSession?.id ?? ""}
                onChange={(event) => setSelectedSessionId(event.target.value)}
                className="h-9 w-full min-w-0 rounded-md border bg-background px-3 text-sm"
              >
                <option value="">Select session</option>
                {sessions.map((session) => (
                  <option key={session.id} value={session.id}>
                    {accountNames.get(session.master_account_id) ?? session.master_account_id} - {session.status}
                  </option>
                ))}
              </select>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Button
                  className="w-full min-w-0"
                  variant="outline"
                  onClick={() => activeSession && controlSession.mutate({sessionId: activeSession.id, action: "pause"})}
                  disabled={!activeSession || activeSession.status !== "RUNNING" || controlSession.isPending}
                >
                  <Pause className="h-4 w-4" />
                  Pause
                </Button>
                <Button
                  className="w-full min-w-0"
                  variant="outline"
                  onClick={() => activeSession && controlSession.mutate({sessionId: activeSession.id, action: "resume"})}
                  disabled={!activeSession || activeSession.status !== "PAUSED" || controlSession.isPending}
                >
                  <RotateCcw className="h-4 w-4" />
                  Resume
                </Button>
                <Button
                  className="w-full min-w-0"
                  variant="destructive"
                  onClick={() => activeSession && controlSession.mutate({sessionId: activeSession.id, action: "stop"})}
                  disabled={!activeSession || activeSession.status === "STOPPED" || controlSession.isPending}
                >
                  <Square className="h-4 w-4" />
                  Stop
                </Button>
                <Button
                  className="w-full min-w-0"
                  variant="outline"
                  onClick={() => {
                    if (!activeSession) return;
                    const ok = window.confirm("Delete this live copy session and its captured events/orders?");
                    if (ok) deleteSession.mutate(activeSession.id);
                  }}
                  disabled={!activeSession || deleteSession.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                  Delete
                </Button>
              </div>
              {activeSession ? (
                <div className="grid gap-2 rounded-md border p-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Status</span>
                    <Badge>{activeSession.status}</Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Mode</span>
                    <span className="flex items-center gap-2">
                      <ShieldCheck className="h-4 w-4 text-muted-foreground" />
                      {activeSession.dry_run ? "Dry run" : "Live orders"}
                    </span>
                  </div>
                  {activeSession.last_error ? <div className="break-words text-destructive">{activeSession.last_error}</div> : null}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Stream Status</CardTitle>
              <RadioTower className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent className="grid gap-3 text-sm">
              <div className="grid min-w-0 gap-2 rounded-md border p-3">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Connection</span>
                  <Badge>{streamStatus?.is_connected ? "CONNECTED" : "DISCONNECTED"}</Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Modules</span>
                  <Badge>{streamStatus?.module_ready ? "READY" : "PENDING"}</Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Ack subscribe</span>
                  <Badge>{streamStatus?.ack_subscription_sent ? "SENT" : "PENDING"}</Badge>
                </div>
                <div className="grid gap-1 text-xs text-muted-foreground">
                  <span>Messages: {streamStatus?.messages_received ?? 0}</span>
                  <span>Ack: {streamStatus?.ack_messages_received ?? 0}</span>
                  <span>Feed: {streamStatus?.feed_messages_received ?? 0}</span>
                  <span>Last: {streamStatus?.last_message_at ?? "-"}</span>
                  <span>Customer: {String(streamStatus?.customer_id_present ?? false)}</span>
                  <span>Proxy: {String(streamStatus?.proxy_configured ?? false)}</span>
                </div>
                {streamStatus?.last_error ? <div className="break-words text-destructive">{streamStatus.last_error}</div> : null}
              </div>
              {streamStatus?.last_sent_payload ? (
                <pre className="max-h-36 min-w-0 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted p-3 text-xs">
                  {JSON.stringify(streamStatus.last_sent_payload, null, 2)}
                </pre>
              ) : null}
              {sentMessages.length ? (
                <div className="grid max-h-72 min-w-0 gap-2 overflow-auto pr-1">
                  {sentMessages.map((message) => (
                    <div key={diagnosticKey("sent", message.type, message.sent_at, message.payload)} className="min-w-0 overflow-hidden rounded-md border p-3">
                      <div className="mb-2 flex min-w-0 items-center justify-between gap-2">
                        <Badge>{message.type.toUpperCase()}</Badge>
                        <span className="min-w-0 truncate text-right text-xs text-muted-foreground">{message.sent_at}</span>
                      </div>
                      <pre className="max-h-28 min-w-0 overflow-auto whitespace-pre-wrap break-words text-xs text-muted-foreground">
                        {JSON.stringify(message.payload, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              ) : null}
              {recentMessages.length ? (
                <div className="grid max-h-80 min-w-0 gap-2 overflow-auto pr-1">
                  {recentMessages.map((message) => (
                    <div key={diagnosticKey("received", message.type, message.received_at, message.payload)} className="min-w-0 overflow-hidden rounded-md border p-3">
                      <div className="mb-2 flex min-w-0 items-center justify-between gap-2">
                        <Badge>{message.type.toUpperCase()}</Badge>
                        <span className="min-w-0 truncate text-right text-xs text-muted-foreground">{message.received_at}</span>
                      </div>
                      <pre className="max-h-28 min-w-0 overflow-auto whitespace-pre-wrap break-words text-xs text-muted-foreground">
                        {JSON.stringify(message.payload, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>

          {warnings.length ? (
            <Card>
              <CardHeader>
                <CardTitle>Preflight Warnings</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="grid max-h-52 gap-2 overflow-auto pr-1 text-sm text-muted-foreground">
                  {warnings.map((warning) => (
                    <li key={warning} className="flex gap-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      <span className="min-w-0 break-words">{warning}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
        </div>

        <div className="grid min-w-0 content-start gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Master Trade Events</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="max-h-[360px] min-w-0 overflow-auto rounded-md border">
                <Table className="min-w-[760px]">
                  <THead>
                    <TR>
                      <TH>Symbol</TH>
                      <TH>Side</TH>
                      <TH>Qty</TH>
                      <TH>Price</TH>
                      <TH>Status</TH>
                      <TH>Order</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {events.length ? (
                      events.map((event) => (
                        <TR key={event.id}>
                          <TD className="whitespace-nowrap font-medium">{event.exchange}:{event.symbol}</TD>
                          <TD>{event.side}</TD>
                          <TD>{event.quantity}</TD>
                          <TD>{event.price}</TD>
                          <TD>
                              <Badge>{event.copied_status}</Badge>
                            </TD>
                          <TD className="max-w-[220px] truncate font-mono text-xs">
                            {event.external_trade_id ?? event.external_order_id ?? "-"}
                          </TD>
                        </TR>
                      ))
                    ) : (
                      <TR>
                        <TD colSpan={6} className="h-32 text-center text-sm text-muted-foreground">
                          No master trade events captured yet
                        </TD>
                      </TR>
                    )}
                  </TBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Copied Order Attempts</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="max-h-[360px] min-w-0 overflow-auto rounded-md border">
                <Table className="min-w-[760px]">
                  <THead>
                    <TR>
                      <TH>Copy Account</TH>
                      <TH>Status</TH>
                      <TH>Child Order</TH>
                      <TH>Error</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {copiedOrders.length ? (
                      copiedOrders.map((order) => (
                        <TR key={order.id}>
                          <TD className="max-w-[240px] truncate">{accountNames.get(order.copier_account_id) ?? order.copier_account_id}</TD>
                          <TD>
                            <Badge>{order.status}</Badge>
                          </TD>
                          <TD className="max-w-[200px] truncate font-mono text-xs">{order.child_order_id ?? "-"}</TD>
                          <TD className="max-w-md whitespace-normal break-words text-muted-foreground">{order.error_message ?? "-"}</TD>
                        </TR>
                      ))
                    ) : (
                      <TR>
                        <TD colSpan={4} className="h-32 text-center text-sm text-muted-foreground">
                          No copied order attempts yet
                        </TD>
                      </TR>
                    )}
                  </TBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </Page>
  );
}
