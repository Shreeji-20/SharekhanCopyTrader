"use client";

import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/data-table";
import { Page } from "@/components/layout/page";
import { apiFetch } from "@/lib/api";

type CopyOrder = {
  id: string;
  master_order_id: string;
  copy_account_id: string;
  broker_order_id: string | null;
  status: string;
  calculated_quantity: number;
  calculated_price: string;
  retry_count: number;
  created_at: string;
};

type Account = {
  id: string;
  account_name: string;
};

export default function CopyOrdersPage() {
  const {data: orders = [], isLoading} = useQuery({
    queryKey: ["copy-orders"],
    queryFn: () => apiFetch<CopyOrder[]>("/orders/copy")
  });
  const {data: accounts = []} = useQuery({
    queryKey: ["accounts"],
    queryFn: () => apiFetch<Account[]>("/accounts")
  });
  const accountNames = new Map(accounts.map((account) => [account.id, account.account_name]));
  const rows = orders.map((order) => ({
    account: accountNames.get(order.copy_account_id) ?? order.copy_account_id,
    quantity: order.calculated_quantity,
    price: order.calculated_price,
    status: order.status,
    retry: order.retry_count,
    order: order.broker_order_id ?? order.id
  }));

  return (
    <Page title="Copy Orders">
      <DataTable rows={rows} columns={["account", "quantity", "price", "status", "retry", "order"]} emptyMessage={isLoading ? "Loading copy orders..." : "No copy orders yet"} />
    </Page>
  );
}
