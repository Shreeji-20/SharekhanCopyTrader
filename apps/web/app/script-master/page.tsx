"use client";

import type React from "react";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bookmark, Loader2, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Page } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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

type ScriptMasterInstrument = {
  id: string | null;
  exchange: string;
  segment: string | null;
  scrip_code: string;
  trading_symbol: string;
  symbol_name: string | null;
  underlying_symbol: string | null;
  instrument_type: string | null;
  option_type: string | null;
  strike_price: string | null;
  expiry_date: string | null;
  lot_size: number | null;
  tick_size: string | null;
  isin: string | null;
  raw_payload_json: Record<string, unknown>;
  refreshed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

type ScriptMasterSearchResult = ScriptMasterInstrument & {
  is_watchlisted: boolean;
  watchlist_id: string | null;
};

type WatchlistItem = {
  id: string;
  account_id: string;
  instrument: ScriptMasterInstrument;
  created_at: string;
};

type Tab = "search" | "watchlist";

function value(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function rawPayloadText(payload: Record<string, unknown>) {
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

function InstrumentRows({
  instruments,
  action,
  emptyMessage,
  loading
}: {
  instruments: ScriptMasterInstrument[];
  action: (instrument: ScriptMasterInstrument) => React.ReactNode;
  emptyMessage: string;
  loading?: boolean;
}) {
  return (
    <div className="min-w-0 overflow-auto rounded-md border">
      <Table className="min-w-[1320px]">
        <THead>
          <TR>
            <TH>Script</TH>
            <TH>Token</TH>
            <TH>Exchange</TH>
            <TH>Segment</TH>
            <TH>Instrument</TH>
            <TH>Lot</TH>
            <TH>Tick</TH>
            <TH>Expiry</TH>
            <TH>Strike</TH>
            <TH>Option</TH>
            <TH>ISIN</TH>
            <TH>Raw</TH>
            <TH>Action</TH>
          </TR>
        </THead>
        <TBody>
          {loading ? (
            <TR>
              <TD colSpan={13} className="h-32 text-center text-sm text-muted-foreground">
                Loading scripts...
              </TD>
            </TR>
          ) : instruments.length ? (
            instruments.map((instrument) => (
              <TR key={`${instrument.exchange}-${instrument.scrip_code}-${instrument.id ?? "snapshot"}`}>
                <TD className="max-w-[220px]">
                  <div className="truncate font-medium">{instrument.trading_symbol}</div>
                  <div className="truncate text-xs text-muted-foreground">{value(instrument.symbol_name ?? instrument.underlying_symbol)}</div>
                </TD>
                <TD className="whitespace-nowrap font-mono text-xs">{instrument.scrip_code}</TD>
                <TD>
                  <Badge>{instrument.exchange}</Badge>
                </TD>
                <TD>{value(instrument.segment)}</TD>
                <TD>{value(instrument.instrument_type)}</TD>
                <TD>{value(instrument.lot_size)}</TD>
                <TD>{value(instrument.tick_size)}</TD>
                <TD className="whitespace-nowrap">{value(instrument.expiry_date)}</TD>
                <TD>{value(instrument.strike_price)}</TD>
                <TD>{value(instrument.option_type)}</TD>
                <TD className="max-w-[160px] truncate font-mono text-xs">{value(instrument.isin)}</TD>
                <TD className="max-w-[260px]">
                  <details>
                    <summary className="cursor-pointer text-xs text-muted-foreground">Fields</summary>
                    <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-md border bg-muted p-2 text-xs text-muted-foreground">
                      {rawPayloadText(instrument.raw_payload_json)}
                    </pre>
                  </details>
                </TD>
                <TD>{action(instrument)}</TD>
              </TR>
            ))
          ) : (
            <TR>
              <TD colSpan={13} className="h-32 text-center text-sm text-muted-foreground">
                {emptyMessage}
              </TD>
            </TR>
          )}
        </TBody>
      </Table>
    </div>
  );
}

export default function ScriptMasterPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("search");
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [addingInstrumentId, setAddingInstrumentId] = useState<string | null>(null);
  const [deletingWatchlistId, setDeletingWatchlistId] = useState<string | null>(null);

  const {data: accounts = [], isLoading: accountsLoading} = useQuery({
    queryKey: ["accounts"],
    queryFn: () => apiFetch<Account[]>("/accounts")
  });

  const accountOptions = useMemo(
    () => accounts.filter((account) => account.is_active),
    [accounts]
  );

  useEffect(() => {
    if (!selectedAccountId && accountOptions.length) {
      setSelectedAccountId(accountOptions[0].id);
    }
  }, [accountOptions, selectedAccountId]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 350);
    return () => window.clearTimeout(timer);
  }, [query]);

  const searchEnabled = Boolean(selectedAccountId && debouncedQuery.length >= 2);
  const {
    data: searchResults = [],
    isFetching: searchLoading,
    isError: searchError,
    refetch: refetchSearch
  } = useQuery({
    queryKey: ["script-master-search", selectedAccountId, debouncedQuery],
    enabled: searchEnabled,
    queryFn: () =>
      apiFetch<ScriptMasterSearchResult[]>(
        `/script-master/search?query=${encodeURIComponent(debouncedQuery)}&account_id=${encodeURIComponent(selectedAccountId)}`
      ),
    retry: false
  });

  const {
    data: watchlist = [],
    isFetching: watchlistLoading,
    isError: watchlistError,
    refetch: refetchWatchlist
  } = useQuery({
    queryKey: ["script-master-watchlist", selectedAccountId],
    enabled: Boolean(selectedAccountId),
    queryFn: () => apiFetch<WatchlistItem[]>(`/script-master/watchlist?account_id=${encodeURIComponent(selectedAccountId)}`),
    retry: false
  });

  const addToWatchlist = useMutation({
    mutationFn: (instrument: ScriptMasterInstrument) => {
      if (!instrument.id) throw new Error("Script Master instrument is missing an id.");
      setAddingInstrumentId(instrument.id);
      return apiFetch<WatchlistItem>("/script-master/watchlist", {
        method: "POST",
        body: JSON.stringify({account_id: selectedAccountId, instrument_id: instrument.id})
      });
    },
    onSuccess: () => {
      toast.success("Script added to watchlist.");
      void queryClient.invalidateQueries({queryKey: ["script-master-search"]});
      void queryClient.invalidateQueries({queryKey: ["script-master-watchlist"]});
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not add script."),
    onSettled: () => setAddingInstrumentId(null)
  });

  const removeFromWatchlist = useMutation({
    mutationFn: (itemId: string) => {
      setDeletingWatchlistId(itemId);
      return apiFetch<void>(`/script-master/watchlist/${itemId}`, {method: "DELETE"});
    },
    onSuccess: () => {
      toast.success("Script removed from watchlist.");
      void queryClient.invalidateQueries({queryKey: ["script-master-search"]});
      void queryClient.invalidateQueries({queryKey: ["script-master-watchlist"]});
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not remove script."),
    onSettled: () => setDeletingWatchlistId(null)
  });

  const selectedAccount = accountOptions.find((account) => account.id === selectedAccountId);
  const watchlistByInstrumentKey = useMemo(() => {
    return new Map(watchlist.map((item) => [`${item.instrument.exchange}:${item.instrument.scrip_code}`, item]));
  }, [watchlist]);
  const searchEmptyMessage = !selectedAccountId
    ? "Select an account"
    : debouncedQuery.length < 2
      ? "Type at least 2 characters"
      : searchError
        ? "Search failed"
        : "No scripts matched";
  const watchlistEmptyMessage = !selectedAccountId ? "Select an account" : watchlistError ? "Watchlist failed to load" : "No saved scripts";

  return (
    <Page
      title="Script Master"
      actions={
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <select
            value={selectedAccountId}
            onChange={(event) => setSelectedAccountId(event.target.value)}
            className="h-9 min-w-52 rounded-md border bg-background px-3 text-sm"
            disabled={accountsLoading}
          >
            <option value="">Select account</option>
            {accountOptions.map((account) => (
              <option key={account.id} value={account.id}>
                {account.account_name}
              </option>
            ))}
          </select>
          <Button
            variant="outline"
            size="icon"
            title="Refresh"
            aria-label="Refresh"
            onClick={() => {
              if (tab === "search") void refetchSearch();
              if (tab === "watchlist") void refetchWatchlist();
            }}
            disabled={tab === "search" ? !searchEnabled : !selectedAccountId}
          >
            <RefreshCw className={`h-4 w-4 ${searchLoading || watchlistLoading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      }
    >
      <div className="grid gap-4">
        <Card>
          <CardContent className="grid gap-3 pt-4">
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
              <div className="relative min-w-0">
                <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search by script name"
                  className="pl-9"
                />
              </div>
              <div className="grid h-9 grid-cols-2 rounded-md border bg-muted p-1">
                {(["search", "watchlist"] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={
                      tab === value
                        ? "rounded-sm bg-background px-3 text-xs font-medium shadow-sm"
                        : "rounded-sm px-3 text-xs font-medium text-muted-foreground"
                    }
                    onClick={() => setTab(value)}
                  >
                    {value === "search" ? "Search" : "Watch List"}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge>{selectedAccount ? selectedAccount.account_type : "ACCOUNT"}</Badge>
              <span>{selectedAccount?.customer_id ?? "-"}</span>
            </div>
          </CardContent>
        </Card>

        {tab === "search" ? (
          <Card>
            <CardHeader>
              <CardTitle>Search Results</CardTitle>
              <Badge>{searchResults.length}</Badge>
            </CardHeader>
            <CardContent>
              <InstrumentRows
                instruments={searchResults}
                loading={searchLoading}
                emptyMessage={searchEmptyMessage}
                action={(instrument) => {
                  const searchResult = instrument as ScriptMasterSearchResult;
                  const existing = watchlistByInstrumentKey.get(`${instrument.exchange}:${instrument.scrip_code}`);
                  const added = searchResult.is_watchlisted || Boolean(existing);
                  const loading = addingInstrumentId === instrument.id;
                  return (
                    <Button
                      size="sm"
                      variant={added ? "outline" : "default"}
                      disabled={added || loading || !selectedAccountId}
                      onClick={() => addToWatchlist.mutate(instrument)}
                    >
                      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : added ? <Bookmark className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
                      {loading ? "Loading" : added ? "Added" : "Add"}
                    </Button>
                  );
                }}
              />
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>Watch List</CardTitle>
              <Badge>{watchlist.length}</Badge>
            </CardHeader>
            <CardContent>
              <InstrumentRows
                instruments={watchlist.map((item) => item.instrument)}
                loading={watchlistLoading}
                emptyMessage={watchlistEmptyMessage}
                action={(instrument) => {
                  const item = watchlistByInstrumentKey.get(`${instrument.exchange}:${instrument.scrip_code}`);
                  const loading = item ? deletingWatchlistId === item.id : false;
                  return (
                    <Button
                      size="icon"
                      variant="outline"
                      title="Remove"
                      aria-label="Remove"
                      disabled={!item || loading}
                      onClick={() => item && removeFromWatchlist.mutate(item.id)}
                    >
                      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                    </Button>
                  );
                }}
              />
            </CardContent>
          </Card>
        )}
      </div>
    </Page>
  );
}
