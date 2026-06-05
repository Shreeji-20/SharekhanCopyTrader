"use client";

import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/data-table";
import { Page } from "@/components/layout/page";
import { SharekhanLiveData } from "@/components/sharekhan-live-data";
import { apiFetch } from "@/lib/api";

type Trade = {
  id: string;
  broker_account_id: string;
  broker_trade_id: string | null;
  exchange: string;
  scrip_code: string;
  trading_symbol: string;
  transaction_type: string;
  quantity: number;
  price: string;
  synced_at: string;
};

type Account = {
  id: string;
  account_name: string;
};

export default function TradesPage() {
  const {data: trades = [], isLoading} = useQuery({
    queryKey: ["trades"],
    queryFn: () => apiFetch<Trade[]>("/trades")
  });
  const {data: accounts = []} = useQuery({
    queryKey: ["accounts"],
    queryFn: () => apiFetch<Account[]>("/accounts")
  });
  const accountNames = new Map(accounts.map((account) => [account.id, account.account_name]));
  const rows = trades.map((trade) => ({
    symbol: trade.trading_symbol,
    side: trade.transaction_type,
    quantity: trade.quantity,
    price: trade.price,
    account: accountNames.get(trade.broker_account_id) ?? trade.broker_account_id,
    trade: trade.broker_trade_id ?? trade.id
  }));

  return (
    <Page title="Trades">
      <div className="grid gap-4">
        <SharekhanLiveData
          title="Live Sharekhan Trade Book"
          description="Fetches the documented Sharekhan trades endpoint for the selected logged-in account."
          endpoint={(accountId) => `/accounts/${accountId}/sharekhan/trades`}
        />
        <DataTable rows={rows} columns={["symbol", "side", "quantity", "price", "account", "trade"]} emptyMessage={isLoading ? "Loading trades..." : "No stored trades yet"} />
      </div>
    </Page>
  );
}
