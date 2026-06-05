"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
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
  login_id: string | null;
  access_token: string | null;
  is_active: boolean;
};

type CopySetting = {
  sizing_mode: string;
  multiplier: string;
  fixed_qty: number | null;
  max_qty: number | null;
  price_mode: string;
  is_enabled: boolean;
};

type CopyGroupMember = {
  id: string;
  copy_group_id: string;
  copy_account_id: string;
  copy_account: Account;
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

export default function CopyGroupDetailPage() {
  const params = useParams<{id: string}>();
  const queryClient = useQueryClient();
  const [copyAccountId, setCopyAccountId] = useState("");

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

  const availableCopyAccounts = useMemo(() => {
    const existing = new Set(group?.members.map((member) => member.copy_account_id) ?? []);
    return accounts.filter((account) => account.account_type === "COPY" && !existing.has(account.id));
  }, [accounts, group]);

  const addMember = useMutation({
    mutationFn: () =>
      apiFetch<CopyGroupMember>(`/copy-groups/${params.id}/members`, {
        method: "POST",
        body: JSON.stringify({copy_account_id: copyAccountId, is_enabled: true})
      }),
    onSuccess: () => {
      toast.success("Copy account added.");
      setCopyAccountId("");
      void queryClient.invalidateQueries({queryKey: ["copy-group", params.id]});
      void queryClient.invalidateQueries({queryKey: ["copy-group-validation", params.id]});
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not add copy account.")
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
    addMember.mutate();
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
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <div className="grid gap-4">
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

        <Card>
          <CardHeader>
            <CardTitle>Copy Members</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <THead>
                  <TR>
                    <TH>Account</TH>
                    <TH>Login</TH>
                    <TH>Sizing</TH>
                    <TH>Price</TH>
                    <TH>Status</TH>
                    <TH className="w-16" />
                  </TR>
                </THead>
                <TBody>
                  {group?.members.length ? (
                    group.members.map((member) => (
                      <TR key={member.id}>
                        <TD className="font-medium">{member.copy_account.account_name}</TD>
                        <TD>{member.copy_account.access_token ? "Logged in" : "Login required"}</TD>
                        <TD>
                          {member.copy_setting?.sizing_mode ?? "SAME_QTY"}
                          {member.copy_setting?.sizing_mode === "MULTIPLIER" ? ` x${member.copy_setting.multiplier}` : ""}
                        </TD>
                        <TD>{member.copy_setting?.price_mode ?? "SAME_PRICE"}</TD>
                        <TD>
                          <Badge>{member.is_enabled && member.copy_account.is_active ? "ACTIVE" : "INACTIVE"}</Badge>
                        </TD>
                        <TD>
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
                        </TD>
                      </TR>
                    ))
                  ) : (
                    <TR>
                      <TD colSpan={6} className="h-32 text-center text-sm text-muted-foreground">
                        {isLoading ? "Loading members..." : "No copy accounts in this group"}
                      </TD>
                    </TR>
                  )}
                </TBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>
    </Page>
  );
}
