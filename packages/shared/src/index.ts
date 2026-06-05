export const ACCOUNT_TYPES = ["MASTER", "COPY"] as const;
export const COPY_ORDER_STATUSES = ["PENDING", "SENT", "SUCCESS", "FAILED", "SKIPPED", "RETRYING"] as const;
export const SIZING_MODES = ["SAME_QTY", "MULTIPLIER", "FIXED_QTY", "PERCENT_CAPITAL"] as const;
export const PRICE_MODES = ["SAME_PRICE", "MARKET", "LIMIT_WITH_SLIPPAGE"] as const;

export type AccountType = (typeof ACCOUNT_TYPES)[number];
export type CopyOrderStatus = (typeof COPY_ORDER_STATUSES)[number];
export type SizingMode = (typeof SIZING_MODES)[number];
export type PriceMode = (typeof PRICE_MODES)[number];

export type BrokerAccountSummary = {
  id: string;
  accountName: string;
  customerId: string;
  accountType: AccountType;
  isActive: boolean;
  lastConnectedAt?: string | null;
};

export type DashboardMetrics = {
  masterOrdersToday: number;
  successfulCopiedOrders: number;
  failedCopyOrders: number;
  activeCopyAccounts: number;
  openPositions: number;
  totalPnl: number;
  brokerConnectionStatus: "CONNECTED" | "DEGRADED" | "DISCONNECTED";
};

