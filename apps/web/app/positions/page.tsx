"use client";

import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/data-table";
import { Page } from "@/components/layout/page";
import { SharekhanLiveData } from "@/components/sharekhan-live-data";
import { apiFetch } from "@/lib/api";

type Position = {
  id: string;
  broker_account_id: string;
  exchange: string;
  scrip_code: string;
  trading_symbol: string;
  quantity: number;
  avg_price: string;
  pnl: string;
  synced_at: string;
};

type Account = {
  id: string;
  account_name: string;
};

export default function PositionsPage() {
  const {data: positions = [], isLoading} = useQuery({
    queryKey: ["positions"],
    queryFn: () => apiFetch<Position[]>("/positions")
  });
  const {data: accounts = []} = useQuery({
    queryKey: ["accounts"],
    queryFn: () => apiFetch<Account[]>("/accounts")
  });
  const accountNames = new Map(accounts.map((account) => [account.id, account.account_name]));
  const rows = positions.map((position) => ({
    symbol: position.trading_symbol,
    account: accountNames.get(position.broker_account_id) ?? position.broker_account_id,
    quantity: position.quantity,
    avg: position.avg_price,
    pnl: position.pnl,
    exchange: position.exchange
  }));

  return (
    <Page title="Positions">
      <div className="grid gap-4">
        <SharekhanLiveData
          title="Live Sharekhan Positions / Trades"
          description="Fetches the documented Sharekhan `/skapi/services/trades/{customerId}` workflow through the selected logged-in account."
          endpoint={(accountId) => `/accounts/${accountId}/sharekhan/trades`}
        />
        <DataTable rows={rows} columns={["symbol", "account", "quantity", "avg", "pnl", "exchange"]} emptyMessage={isLoading ? "Loading positions..." : "No stored positions yet"} />
      </div>
    </Page>
  );
}
