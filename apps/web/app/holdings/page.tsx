"use client";

import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/data-table";
import { Page } from "@/components/layout/page";
import { SharekhanLiveData } from "@/components/sharekhan-live-data";
import { apiFetch } from "@/lib/api";

type Holding = {
  id: string;
  broker_account_id: string;
  raw_payload: Record<string, unknown>;
  synced_at: string;
};

type Account = {
  id: string;
  account_name: string;
};

function holdingValue(payload: Record<string, unknown>) {
  const value = payload.value ?? payload.marketValue ?? payload.totalValue ?? payload.holdingValue;
  return value == null ? "-" : String(value);
}

export default function HoldingsPage() {
  const {data: holdings = [], isLoading} = useQuery({
    queryKey: ["holdings"],
    queryFn: () => apiFetch<Holding[]>("/holdings")
  });
  const {data: accounts = []} = useQuery({
    queryKey: ["accounts"],
    queryFn: () => apiFetch<Account[]>("/accounts")
  });
  const accountNames = new Map(accounts.map((account) => [account.id, account.account_name]));
  const rows = holdings.map((holding) => ({
    account: accountNames.get(holding.broker_account_id) ?? holding.broker_account_id,
    value: holdingValue(holding.raw_payload),
    synced: new Date(holding.synced_at).toLocaleString("en-IN"),
    id: holding.id
  }));

  return (
    <Page title="Holdings">
      <div className="grid gap-4">
        <SharekhanLiveData
          title="Live Sharekhan Holdings"
          description="Fetches the documented Sharekhan holdings endpoint for the selected logged-in account."
          endpoint={(accountId) => `/accounts/${accountId}/sharekhan/holdings`}
        />
        <DataTable rows={rows} columns={["account", "value", "synced", "id"]} emptyMessage={isLoading ? "Loading holdings..." : "No stored holdings yet"} />
      </div>
    </Page>
  );
}
