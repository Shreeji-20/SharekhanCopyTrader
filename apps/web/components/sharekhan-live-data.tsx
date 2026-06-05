"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { DataTable } from "@/components/data-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";

type Account = {
  id: string;
  account_name: string;
  customer_id?: string | null;
  login_id?: string | null;
  access_token?: string | null;
};

type RawPayload = Record<string, unknown>;

function scalar(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return value;
  return JSON.stringify(value);
}

function payloadRows(payload: unknown): RawPayload[] {
  const value = payload && typeof payload === "object" && "data" in payload ? (payload as {data?: unknown}).data : payload;
  if (Array.isArray(value)) return value.filter((item): item is RawPayload => Boolean(item) && typeof item === "object" && !Array.isArray(item));
  if (value && typeof value === "object") {
    const objectValue = value as RawPayload;
    for (const key of ["orders", "reports", "trades", "positions", "holdings", "items", "records"]) {
      const nested = objectValue[key];
      if (Array.isArray(nested)) {
        return nested.filter((item): item is RawPayload => Boolean(item) && typeof item === "object" && !Array.isArray(item));
      }
    }
    return [objectValue];
  }
  return [];
}

function rowsAndColumns(payload: unknown) {
  const rawRows = payloadRows(payload);
  const columns = Array.from(new Set(rawRows.flatMap((row) => Object.keys(row)))).slice(0, 8);
  const fallbackColumns = columns.length ? columns : ["payload"];
  const rows = rawRows.map((row) => {
    if (!columns.length) return {payload: scalar(row)};
    return Object.fromEntries(fallbackColumns.map((column) => [column, scalar(row[column])]));
  });
  return {rows, columns: fallbackColumns};
}

export function SharekhanLiveData({
  title,
  description,
  endpoint
}: {
  title: string;
  description: string;
  endpoint: (accountId: string) => string;
}) {
  const {data: accounts = []} = useQuery({
    queryKey: ["accounts"],
    queryFn: () => apiFetch<Account[]>("/accounts")
  });
  const connectedAccounts = accounts.filter((account) => account.access_token);
  const [accountId, setAccountId] = useState("");
  const selectedAccountId = accountId || connectedAccounts[0]?.id || "";
  const query = useQuery({
    queryKey: ["sharekhan-live-data", title, selectedAccountId],
    queryFn: () => apiFetch<unknown>(endpoint(selectedAccountId)),
    enabled: Boolean(selectedAccountId),
    staleTime: 10_000
  });
  const table = useMemo(() => rowsAndColumns(query.data), [query.data]);

  return (
    <Card>
      <CardHeader className="border-b">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>{title}</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">{description}</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={selectedAccountId}
              onChange={(event) => setAccountId(event.target.value)}
              className="h-9 min-w-52 rounded-md border bg-background px-3 text-sm"
            >
              {connectedAccounts.length ? null : <option value="">No logged-in accounts</option>}
              {connectedAccounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.account_name}
                </option>
              ))}
            </select>
            <Button variant="outline" size="icon" title="Refresh" aria-label="Refresh" disabled={!selectedAccountId} onClick={() => void query.refetch()}>
              <RefreshCw className={`h-4 w-4 ${query.isFetching ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-4">
        {query.isError ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            {query.error instanceof Error ? query.error.message : "Sharekhan data could not be loaded."}
          </div>
        ) : (
          <DataTable
            rows={table.rows}
            columns={table.columns}
            emptyMessage={query.isLoading ? "Loading Sharekhan data..." : "No live Sharekhan records returned"}
          />
        )}
      </CardContent>
    </Card>
  );
}
