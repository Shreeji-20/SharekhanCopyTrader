"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { DataTable } from "@/components/data-table";
import { Page } from "@/components/layout/page";
import { SharekhanLiveData } from "@/components/sharekhan-live-data";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";

type MasterOrder = {
  id: string;
  broker_order_id: string;
  exchange: string;
  scrip_code: string;
  trading_symbol: string;
  transaction_type: string;
  quantity: number;
  price: string;
  status: string;
  created_at: string;
};

type BrokerAccount = {
  id: string;
  account_name: string;
  customer_id: string | null;
  login_id: string | null;
  access_token: string | null;
};

type BrokerOrderResponse = {
  ok: boolean;
  normalized?: {
    broker_order_id?: string | null;
    status?: string | number | null;
    message?: string | null;
  };
  data?: Record<string, unknown>;
};

function OrderTicket() {
  const [accountId, setAccountId] = useState("");
  const {data: accounts = []} = useQuery({
    queryKey: ["accounts"],
    queryFn: () => apiFetch<BrokerAccount[]>("/accounts")
  });
  const connectedAccounts = accounts.filter((account) => account.access_token);
  const selectedAccount = connectedAccounts.find((account) => account.id === accountId) ?? connectedAccounts[0];
  const order = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiFetch<BrokerOrderResponse>(`/accounts/${selectedAccount?.id}/sharekhan/orders/place`, {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    onSuccess: (response) => {
      const brokerOrderId = response.normalized?.broker_order_id;
      toast.success(brokerOrderId ? `Order sent: ${brokerOrderId}` : "Order sent to Sharekhan");
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Order placement failed")
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedAccount) {
      toast.error("No logged-in Sharekhan account available");
      return;
    }
    if (!selectedAccount.customer_id || !selectedAccount.login_id) {
      toast.error("Selected account needs customer ID and login ID from Sharekhan profile");
      return;
    }
    const form = new FormData(event.currentTarget);
    const payload = {
      customerId: selectedAccount.customer_id,
      channelUser: selectedAccount.login_id,
      scripCode: Number(form.get("scripCode")),
      tradingSymbol: String(form.get("tradingSymbol") ?? "").trim().toUpperCase(),
      exchange: String(form.get("exchange") ?? "NC").trim().toUpperCase(),
      transactionType: form.get("transactionType"),
      quantity: Number(form.get("quantity")),
      disclosedQty: 0,
      price: String(form.get("price") ?? "0").trim() || "0",
      triggerPrice: String(form.get("triggerPrice") ?? "0").trim() || "0",
      rmsCode: "ANY",
      afterHour: "N",
      orderType: String(form.get("orderType") ?? "NORMAL").trim().toUpperCase(),
      validity: "GFD",
      requestType: "NEW",
      productType: String(form.get("productType") ?? "INVESTMENT").trim().toUpperCase()
    };
    order.mutate(payload);
  }

  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle>Sharekhan Order Ticket</CardTitle>
      </CardHeader>
      <CardContent className="pt-4">
        <form className="grid gap-3 lg:grid-cols-8" onSubmit={submit}>
          <select
            value={selectedAccount?.id ?? ""}
            onChange={(event) => setAccountId(event.target.value)}
            className="h-9 rounded-md border bg-background px-3 text-sm lg:col-span-2"
          >
            {connectedAccounts.length ? null : <option value="">No logged-in accounts</option>}
            {connectedAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.account_name}
              </option>
            ))}
          </select>
          <Input name="tradingSymbol" placeholder="Symbol" required />
          <Input name="scripCode" type="number" min="1" placeholder="Scrip" required />
          <select name="exchange" defaultValue="NC" className="h-9 rounded-md border bg-background px-3 text-sm">
            <option value="NC">NC</option>
            <option value="NF">NF</option>
            <option value="BC">BC</option>
            <option value="RN">RN</option>
            <option value="MX">MX</option>
          </select>
          <select name="transactionType" defaultValue="B" className="h-9 rounded-md border bg-background px-3 text-sm">
            <option value="B">Buy</option>
            <option value="S">Sell</option>
          </select>
          <Input name="quantity" type="number" min="1" placeholder="Qty" required />
          <Input name="price" type="number" min="0" step="0.01" placeholder="Price" required />
          <Input name="triggerPrice" type="number" min="0" step="0.01" placeholder="Trigger" defaultValue="0" />
          <select name="orderType" defaultValue="NORMAL" className="h-9 rounded-md border bg-background px-3 text-sm">
            <option value="NORMAL">NORMAL</option>
            <option value="NOR">NOR</option>
          </select>
          <select name="productType" defaultValue="INVESTMENT" className="h-9 rounded-md border bg-background px-3 text-sm">
            <option value="INVESTMENT">INVESTMENT</option>
          </select>
          <Button type="submit" disabled={order.isPending || !selectedAccount} className="lg:col-span-2">
            <Send className="h-4 w-4" />
            {order.isPending ? "Sending..." : "Send Order"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export default function MasterOrdersPage() {
  const {data: orders = [], isLoading} = useQuery({
    queryKey: ["master-orders"],
    queryFn: () => apiFetch<MasterOrder[]>("/orders/master")
  });
  const rows = orders.map((order) => ({
    symbol: order.trading_symbol,
    side: order.transaction_type,
    quantity: order.quantity,
    price: order.price,
    status: order.status,
    order: order.broker_order_id || order.id
  }));

  return (
    <Page title="Master Orders">
      <div className="grid gap-4">
        <OrderTicket />
        <SharekhanLiveData
          title="Live Sharekhan Order Book"
          description="Fetches the documented Sharekhan reports endpoint for the selected logged-in account."
          endpoint={(accountId) => `/accounts/${accountId}/sharekhan/reports`}
        />
        <DataTable rows={rows} columns={["symbol", "side", "quantity", "price", "status", "order"]} emptyMessage={isLoading ? "Loading master orders..." : "No stored master orders yet"} />
      </div>
    </Page>
  );
}
