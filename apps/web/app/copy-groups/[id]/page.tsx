"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Page } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";

type Account = {
  id: string;
  account_name: string;
  account_type: "MASTER" | "COPY";
  customer_id: string | null;
  login_id: string | null;
  access_token: string | null;
  is_active: boolean;
};

type CopyGroupAccount = {
  id: string;
  account_name: string;
  account_type: "MASTER" | "COPY";
  customer_id: string | null;
  login_id: string | null;
  has_access_token: boolean;
  is_active: boolean;
};

type SizingMode = "SAME_QTY" | "MULTIPLIER" | "FIXED_QTY" | "PERCENT_CAPITAL";
type PriceMode = "SAME_PRICE" | "MARKET" | "LIMIT_WITH_SLIPPAGE";

type CopySetting = {
  id: string;
  copy_account_id: string;
  copy_group_id: string;
  sizing_mode: SizingMode;
  multiplier: string;
  fixed_qty: number | null;
  capital_percent: string | null;
  min_qty: number | null;
  max_qty: number | null;
  max_trades_per_day: number | null;
  max_daily_loss: string | null;
  max_order_value: string | null;
  allowed_symbols: string[];
  blocked_symbols: string[];
  allowed_transaction_types: string[];
  allowed_product_types: string[];
  product_type_map: Record<string, string>;
  price_mode: PriceMode;
  max_slippage_percent: string | null;
  is_auto_squareoff_enabled: boolean;
  is_enabled: boolean;
};

type CopyGroupMember = {
  id: string;
  copy_group_id: string;
  copy_account_id: string;
  copy_account: CopyGroupAccount;
  copy_setting: CopySetting | null;
  is_enabled: boolean;
  created_at: string;
};

type CopyGroupDetail = {
  id: string;
  name: string;
  description: string | null;
  master_account_id: string;
  master_account_name: string | null;
  is_active: boolean;
  members: CopyGroupMember[];
  created_at: string;
  updated_at: string;
};

type ValidationResult = {
  ok: boolean;
  warnings: string[];
  copy_account_count: number;
};

type RiskDraft = {
  member_enabled: boolean;
  setting_enabled: boolean;
  sizing_mode: SizingMode;
  multiplier: string;
  fixed_qty: string;
  capital_percent: string;
  min_qty: string;
  max_qty: string;
  max_trades_per_day: string;
  max_daily_loss: string;
  max_order_value: string;
  allowed_symbols: string;
  blocked_symbols: string;
  allowed_transaction_types: string[];
  allowed_product_types: string;
  product_type_map: string;
  price_mode: PriceMode;
  max_slippage_percent: string;
  is_auto_squareoff_enabled: boolean;
};

type MemberUpdatePayload = {
  is_enabled: boolean;
  copy_setting: {
    sizing_mode: SizingMode;
    multiplier: string;
    fixed_qty: number | null;
    capital_percent: string | null;
    min_qty: number | null;
    max_qty: number | null;
    max_trades_per_day: number | null;
    max_daily_loss: string | null;
    max_order_value: string | null;
    allowed_symbols: string[];
    blocked_symbols: string[];
    allowed_transaction_types: string[];
    allowed_product_types: string[];
    product_type_map: Record<string, string>;
    price_mode: PriceMode;
    max_slippage_percent: string | null;
    is_auto_squareoff_enabled: boolean;
    is_enabled: boolean;
  };
};

const sizingModes: SizingMode[] = ["SAME_QTY", "MULTIPLIER", "FIXED_QTY", "PERCENT_CAPITAL"];
const priceModes: PriceMode[] = ["SAME_PRICE", "MARKET", "LIMIT_WITH_SLIPPAGE"];

const emptyDraft: RiskDraft = {
  member_enabled: true,
  setting_enabled: true,
  sizing_mode: "SAME_QTY",
  multiplier: "1",
  fixed_qty: "",
  capital_percent: "",
  min_qty: "",
  max_qty: "",
  max_trades_per_day: "",
  max_daily_loss: "",
  max_order_value: "",
  allowed_symbols: "",
  blocked_symbols: "",
  allowed_transaction_types: ["B", "S"],
  allowed_product_types: "",
  product_type_map: "",
  price_mode: "SAME_PRICE",
  max_slippage_percent: "",
  is_auto_squareoff_enabled: false
};

function csv(values: string[]): string {
  return values.join(", ");
}

function parseCsv(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
}

function formatProductMap(value: Record<string, string>): string {
  return Object.entries(value)
    .map(([source, target]) => `${source}:${target}`)
    .join(", ");
}

function parseProductMap(value: string): Record<string, string> {
  const output: Record<string, string> = {};
  for (const entry of value.split(",")) {
    const [source, target] = entry.split(":").map((part) => part?.trim().toUpperCase());
    if (source && target) {
      output[source] = target;
    }
  }
  return output;
}

function valueText(value: string | number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

function optionalInt(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
}

function optionalDecimal(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function draftFromMember(member: CopyGroupMember): RiskDraft {
  const setting = member.copy_setting;
  if (!setting) {
    return {...emptyDraft, member_enabled: member.is_enabled};
  }
  return {
    member_enabled: member.is_enabled,
    setting_enabled: setting.is_enabled,
    sizing_mode: setting.sizing_mode,
    multiplier: valueText(setting.multiplier || "1"),
    fixed_qty: valueText(setting.fixed_qty),
    capital_percent: valueText(setting.capital_percent),
    min_qty: valueText(setting.min_qty),
    max_qty: valueText(setting.max_qty),
    max_trades_per_day: valueText(setting.max_trades_per_day),
    max_daily_loss: valueText(setting.max_daily_loss),
    max_order_value: valueText(setting.max_order_value),
    allowed_symbols: csv(setting.allowed_symbols),
    blocked_symbols: csv(setting.blocked_symbols),
    allowed_transaction_types: setting.allowed_transaction_types.length ? setting.allowed_transaction_types : ["B", "S"],
    allowed_product_types: csv(setting.allowed_product_types),
    product_type_map: formatProductMap(setting.product_type_map),
    price_mode: setting.price_mode,
    max_slippage_percent: valueText(setting.max_slippage_percent),
    is_auto_squareoff_enabled: setting.is_auto_squareoff_enabled
  };
}

function validateDraft(draft: RiskDraft): MemberUpdatePayload | null {
  const multiplier = Number(draft.multiplier);
  if (!Number.isFinite(multiplier) || multiplier <= 0) {
    toast.error("Multiplier must be greater than zero.");
    return null;
  }
  const fixedQty = optionalInt(draft.fixed_qty);
  if (draft.sizing_mode === "FIXED_QTY" && !fixedQty) {
    toast.error("Fixed quantity is required for FIXED_QTY sizing.");
    return null;
  }
  const minQty = optionalInt(draft.min_qty);
  const maxQty = optionalInt(draft.max_qty);
  if (minQty && maxQty && minQty > maxQty) {
    toast.error("Min quantity cannot be greater than max quantity.");
    return null;
  }
  if (!draft.allowed_transaction_types.length) {
    toast.error("Select at least one side.");
    return null;
  }
  return {
    is_enabled: draft.member_enabled,
    copy_setting: {
      sizing_mode: draft.sizing_mode,
      multiplier: draft.multiplier.trim() || "1",
      fixed_qty: fixedQty,
      capital_percent: optionalDecimal(draft.capital_percent),
      min_qty: minQty,
      max_qty: maxQty,
      max_trades_per_day: optionalInt(draft.max_trades_per_day),
      max_daily_loss: optionalDecimal(draft.max_daily_loss),
      max_order_value: optionalDecimal(draft.max_order_value),
      allowed_symbols: parseCsv(draft.allowed_symbols),
      blocked_symbols: parseCsv(draft.blocked_symbols),
      allowed_transaction_types: draft.allowed_transaction_types,
      allowed_product_types: parseCsv(draft.allowed_product_types),
      product_type_map: parseProductMap(draft.product_type_map),
      price_mode: draft.price_mode,
      max_slippage_percent: optionalDecimal(draft.max_slippage_percent),
      is_auto_squareoff_enabled: draft.is_auto_squareoff_enabled,
      is_enabled: draft.setting_enabled
    }
  };
}

export default function CopyGroupDetailPage() {
  const params = useParams<{id: string}>();
  const queryClient = useQueryClient();
  const [copyAccountId, setCopyAccountId] = useState("");
  const [newMemberDraft, setNewMemberDraft] = useState<RiskDraft>(emptyDraft);
  const [drafts, setDrafts] = useState<Record<string, RiskDraft>>({});

  const {data: group, isLoading} = useQuery({
    queryKey: ["copy-group", params.id],
    queryFn: () => apiFetch<CopyGroupDetail>(`/copy-groups/${params.id}`)
  });
  const {data: accounts = []} = useQuery({
    queryKey: ["accounts"],
    queryFn: () => apiFetch<Account[]>("/accounts")
  });
  const {data: validation} = useQuery({
    queryKey: ["copy-group-validation", params.id, group?.master_account_id],
    enabled: Boolean(group),
    queryFn: () =>
      apiFetch<ValidationResult>("/copy-groups/validate", {
        method: "POST",
        body: JSON.stringify({master_account_id: group?.master_account_id, copy_group_ids: [params.id]})
      })
  });

  useEffect(() => {
    if (!group) {
      return;
    }
    setDrafts((current) => {
      const next: Record<string, RiskDraft> = {};
      for (const member of group.members) {
        next[member.id] = current[member.id] ?? draftFromMember(member);
      }
      return next;
    });
  }, [group]);

  const availableCopyAccounts = useMemo(() => {
    const existing = new Set(group?.members.map((member) => member.copy_account_id) ?? []);
    return accounts.filter((account) => account.account_type === "COPY" && !existing.has(account.id));
  }, [accounts, group]);

  const addMember = useMutation({
    mutationFn: (payload: MemberUpdatePayload) =>
      apiFetch<CopyGroupMember>(`/copy-groups/${params.id}/members`, {
        method: "POST",
        body: JSON.stringify({copy_account_id: copyAccountId, ...payload})
      }),
    onSuccess: () => {
      toast.success("Copy account added.");
      setCopyAccountId("");
      setNewMemberDraft(emptyDraft);
      void queryClient.invalidateQueries({queryKey: ["copy-group", params.id]});
      void queryClient.invalidateQueries({queryKey: ["copy-group-validation", params.id]});
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not add copy account.")
  });

  const updateMember = useMutation({
    mutationFn: ({memberId, payload}: {memberId: string; payload: MemberUpdatePayload}) =>
      apiFetch<CopyGroupMember>(`/copy-groups/${params.id}/members/${memberId}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      }),
    onSuccess: () => {
      toast.success("Risk settings saved.");
      void queryClient.invalidateQueries({queryKey: ["copy-group", params.id]});
      void queryClient.invalidateQueries({queryKey: ["copy-group-validation", params.id]});
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not save risk settings.")
  });

  const removeMember = useMutation({
    mutationFn: (memberId: string) => apiFetch<void>(`/copy-groups/${params.id}/members/${memberId}`, {method: "DELETE"}),
    onSuccess: () => {
      toast.success("Copy account removed.");
      void queryClient.invalidateQueries({queryKey: ["copy-group", params.id]});
      void queryClient.invalidateQueries({queryKey: ["copy-group-validation", params.id]});
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not remove copy account.")
  });

  function submitAddMember() {
    if (!copyAccountId) {
      toast.error("Select a copy account first.");
      return;
    }
    const payload = validateDraft(newMemberDraft);
    if (payload) {
      addMember.mutate(payload);
    }
  }

  function patchDraft(memberId: string, patch: Partial<RiskDraft>) {
    setDrafts((current) => ({...current, [memberId]: {...current[memberId], ...patch}}));
  }

  function toggleSide(draft: RiskDraft, side: string): string[] {
    return draft.allowed_transaction_types.includes(side)
      ? draft.allowed_transaction_types.filter((item) => item !== side)
      : [...draft.allowed_transaction_types, side];
  }

  function riskFields(draft: RiskDraft, onChange: (patch: Partial<RiskDraft>) => void) {
    return (
      <div className="grid gap-3">
        <div className="grid gap-3 md:grid-cols-4">
          <label className="grid gap-1 text-xs text-muted-foreground">
            Sizing
            <select
              value={draft.sizing_mode}
              onChange={(event) => onChange({sizing_mode: event.target.value as SizingMode})}
              className="h-9 rounded-md border bg-background px-3 text-sm text-foreground"
            >
              {sizingModes.map((mode) => (
                <option key={mode} value={mode}>
                  {mode}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">
            Multiplier
            <Input value={draft.multiplier} onChange={(event) => onChange({multiplier: event.target.value})} />
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">
            Fixed qty
            <Input value={draft.fixed_qty} onChange={(event) => onChange({fixed_qty: event.target.value})} />
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">
            Capital %
            <Input value={draft.capital_percent} onChange={(event) => onChange({capital_percent: event.target.value})} />
          </label>
        </div>

        <div className="grid gap-3 md:grid-cols-5">
          <label className="grid gap-1 text-xs text-muted-foreground">
            Min qty
            <Input value={draft.min_qty} onChange={(event) => onChange({min_qty: event.target.value})} />
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">
            Max qty
            <Input value={draft.max_qty} onChange={(event) => onChange({max_qty: event.target.value})} />
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">
            Max trades/day
            <Input value={draft.max_trades_per_day} onChange={(event) => onChange({max_trades_per_day: event.target.value})} />
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">
            Max daily loss
            <Input value={draft.max_daily_loss} onChange={(event) => onChange({max_daily_loss: event.target.value})} />
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">
            Max order value
            <Input value={draft.max_order_value} onChange={(event) => onChange({max_order_value: event.target.value})} />
          </label>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <label className="grid gap-1 text-xs text-muted-foreground">
            Price
            <select
              value={draft.price_mode}
              onChange={(event) => onChange({price_mode: event.target.value as PriceMode})}
              className="h-9 rounded-md border bg-background px-3 text-sm text-foreground"
            >
              {priceModes.map((mode) => (
                <option key={mode} value={mode}>
                  {mode}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">
            Slippage %
            <Input value={draft.max_slippage_percent} onChange={(event) => onChange({max_slippage_percent: event.target.value})} />
          </label>
          <div className="grid gap-1 text-xs text-muted-foreground">
            Side
            <div className="flex h-9 items-center gap-2">
              {["B", "S"].map((side) => (
                <button
                  key={side}
                  type="button"
                  onClick={() => onChange({allowed_transaction_types: toggleSide(draft, side)})}
                  className={`h-8 rounded-md border px-3 text-sm ${
                    draft.allowed_transaction_types.includes(side) ? "bg-primary text-primary-foreground" : "bg-background"
                  }`}
                >
                  {side}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <label className="grid gap-1 text-xs text-muted-foreground">
            Allowed symbols
            <Input value={draft.allowed_symbols} onChange={(event) => onChange({allowed_symbols: event.target.value})} />
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">
            Blocked symbols
            <Input value={draft.blocked_symbols} onChange={(event) => onChange({blocked_symbols: event.target.value})} />
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">
            Product types
            <Input value={draft.allowed_product_types} onChange={(event) => onChange({allowed_product_types: event.target.value})} />
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">
            Product map
            <Input value={draft.product_type_map} onChange={(event) => onChange({product_type_map: event.target.value})} />
          </label>
        </div>

        <div className="flex flex-wrap gap-4 text-sm">
          <label className="inline-flex items-center gap-2">
            <input type="checkbox" checked={draft.member_enabled} onChange={(event) => onChange({member_enabled: event.target.checked})} />
            Member enabled
          </label>
          <label className="inline-flex items-center gap-2">
            <input type="checkbox" checked={draft.setting_enabled} onChange={(event) => onChange({setting_enabled: event.target.checked})} />
            Copy enabled
          </label>
          <label className="inline-flex items-center gap-2">
            <input
              type="checkbox"
              checked={draft.is_auto_squareoff_enabled}
              onChange={(event) => onChange({is_auto_squareoff_enabled: event.target.checked})}
            />
            Auto squareoff
          </label>
        </div>
      </div>
    );
  }

  return (
    <Page
      title={group?.name ?? "Copy Group"}
      actions={
        <div className="flex items-center gap-2">
          <Link
            href="/copy-groups"
            className="inline-flex h-9 items-center justify-center gap-2 rounded-md border bg-background px-3 text-sm transition-colors hover:bg-muted"
          >
            <ArrowLeft className="h-4 w-4" />
            Groups
          </Link>
          <Badge>{group?.is_active ? "ACTIVE" : isLoading ? "LOADING" : "INACTIVE"}</Badge>
        </div>
      }
    >
      <div className="grid min-w-0 gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <div className="grid min-w-0 gap-4 content-start">
          <Card>
            <CardHeader>
              <CardTitle>Group Details</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 text-sm">
              <div>
                <div className="text-xs uppercase text-muted-foreground">Master</div>
                <div>{group?.master_account_name ?? group?.master_account_id ?? "-"}</div>
              </div>
              <div>
                <div className="text-xs uppercase text-muted-foreground">Description</div>
                <div className="text-muted-foreground">{group?.description ?? "-"}</div>
              </div>
              <div>
                <div className="text-xs uppercase text-muted-foreground">Members</div>
                <div>{group?.members.length ?? 0}</div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Add Copy Account</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3">
              <select
                value={copyAccountId}
                onChange={(event) => setCopyAccountId(event.target.value)}
                className="h-9 rounded-md border bg-background px-3 text-sm"
              >
                <option value="">Select copy account</option>
                {availableCopyAccounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.account_name}
                  </option>
                ))}
              </select>
              <div className="rounded-md border p-3">{riskFields(newMemberDraft, (patch) => setNewMemberDraft((current) => ({...current, ...patch})))}</div>
              <Button onClick={submitAddMember} disabled={addMember.isPending || !availableCopyAccounts.length}>
                <Plus className="h-4 w-4" />
                Add Member
              </Button>
            </CardContent>
          </Card>

          {validation?.warnings.length ? (
            <Card>
              <CardHeader>
                <CardTitle>Preflight Warnings</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="grid gap-2 text-sm text-muted-foreground">
                  {validation.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
        </div>

        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Copy Members</CardTitle>
          </CardHeader>
          <CardContent className="grid min-w-0 gap-4">
            {group?.members.length ? (
              group.members.map((member) => {
                const draft = drafts[member.id] ?? draftFromMember(member);
                const active = member.is_enabled && member.copy_account.is_active && Boolean(member.copy_setting?.is_enabled ?? true);
                return (
                  <div key={member.id} className="grid min-w-0 gap-4 rounded-md border bg-card/40 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate font-medium">{member.copy_account.account_name}</div>
                        <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                          <span>{member.copy_account.has_access_token ? "Logged in" : "Login required"}</span>
                          <span>{member.copy_account.login_id ?? "No login id"}</span>
                          <span>{member.copy_account.customer_id ?? "No customer id"}</span>
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <Badge>{active ? "ACTIVE" : "INACTIVE"}</Badge>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            const payload = validateDraft(draft);
                            if (payload) {
                              updateMember.mutate({memberId: member.id, payload});
                            }
                          }}
                          disabled={updateMember.isPending}
                        >
                          <Save className="h-4 w-4" />
                          Save
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Remove member"
                          aria-label="Remove member"
                          onClick={() => removeMember.mutate(member.id)}
                          disabled={removeMember.isPending}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                    {riskFields(draft, (patch) => patchDraft(member.id, patch))}
                  </div>
                );
              })
            ) : (
              <div className="h-32 rounded-md border text-center text-sm text-muted-foreground">
                <div className="flex h-full items-center justify-center">{isLoading ? "Loading members..." : "No copy accounts in this group"}</div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </Page>
  );
}
