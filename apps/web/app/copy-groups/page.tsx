"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Page } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";

type CopyGroup = {
  id: string;
  name: string;
  description: string | null;
  master_account_id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type Account = {
  id: string;
  account_name: string;
  account_type: "MASTER" | "COPY";
  customer_id: string | null;
  login_id: string | null;
  access_token: string | null;
  is_active: boolean;
};

export default function CopyGroupsPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [masterAccountId, setMasterAccountId] = useState("");
  const [isActive, setIsActive] = useState(true);

  const {data: groups = [], isLoading} = useQuery({
    queryKey: ["copy-groups"],
    queryFn: () => apiFetch<CopyGroup[]>("/copy-groups")
  });
  const {data: accounts = []} = useQuery({
    queryKey: ["accounts"],
    queryFn: () => apiFetch<Account[]>("/accounts")
  });

  const masters = useMemo(() => accounts.filter((account) => account.account_type === "MASTER"), [accounts]);
  const accountNames = useMemo(
    () => new Map(accounts.map((account) => [account.id, account.account_name])),
    [accounts]
  );

  const createGroup = useMutation({
    mutationFn: () =>
      apiFetch<CopyGroup>("/copy-groups", {
        method: "POST",
        body: JSON.stringify({
          name,
          description: description || null,
          master_account_id: masterAccountId,
          is_active: isActive
        })
      }),
    onSuccess: () => {
      toast.success("Copy group created.");
      setName("");
      setDescription("");
      setIsActive(true);
      void queryClient.invalidateQueries({queryKey: ["copy-groups"]});
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not create copy group.")
  });

  const updateGroup = useMutation({
    mutationFn: ({group, active}: {group: CopyGroup; active: boolean}) =>
      apiFetch<CopyGroup>(`/copy-groups/${group.id}`, {
        method: "PATCH",
        body: JSON.stringify({is_active: active})
      }),
    onSuccess: () => {
      toast.success("Copy group updated.");
      void queryClient.invalidateQueries({queryKey: ["copy-groups"]});
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not update copy group.")
  });

  const deleteGroup = useMutation({
    mutationFn: (groupId: string) => apiFetch<void>(`/copy-groups/${groupId}`, {method: "DELETE"}),
    onSuccess: () => {
      toast.success("Copy group deleted.");
      void queryClient.invalidateQueries({queryKey: ["copy-groups"]});
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not delete copy group.")
  });

  function submitCreate() {
    if (!name.trim() || !masterAccountId) {
      toast.error("Name and master account are required.");
      return;
    }
    createGroup.mutate();
  }

  return (
    <Page title="Copy Groups">
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>New Group</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Group name" />
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Description"
              className="min-h-24 rounded-md border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-ring"
            />
            <select
              value={masterAccountId}
              onChange={(event) => setMasterAccountId(event.target.value)}
              className="h-9 rounded-md border bg-background px-3 text-sm"
            >
              <option value="">Select master account</option>
              {masters.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.account_name}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
              Active group
            </label>
            <Button onClick={submitCreate} disabled={createGroup.isPending}>
              <Plus className="h-4 w-4" />
              Create Group
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Configured Groups</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <THead>
                  <TR>
                    <TH>Name</TH>
                    <TH>Master</TH>
                    <TH>Status</TH>
                    <TH>Description</TH>
                    <TH className="w-48">Actions</TH>
                  </TR>
                </THead>
                <TBody>
                  {groups.length ? (
                    groups.map((group) => (
                      <TR key={group.id}>
                        <TD className="font-medium">{group.name}</TD>
                        <TD>{accountNames.get(group.master_account_id) ?? group.master_account_id}</TD>
                        <TD>
                          <Badge>{group.is_active ? "ACTIVE" : "INACTIVE"}</Badge>
                        </TD>
                        <TD className="max-w-xs truncate text-muted-foreground">{group.description ?? "-"}</TD>
                        <TD>
                          <div className="flex items-center gap-2">
                            <Link
                              href={`/copy-groups/${group.id}`}
                              className="inline-flex h-8 items-center justify-center gap-2 rounded-md border bg-background px-2 text-sm transition-colors hover:bg-muted"
                            >
                              <ExternalLink className="h-4 w-4" />
                              Open
                            </Link>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => updateGroup.mutate({group, active: !group.is_active})}
                              disabled={updateGroup.isPending}
                            >
                              {group.is_active ? "Disable" : "Enable"}
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              title="Delete group"
                              aria-label="Delete group"
                              onClick={() => deleteGroup.mutate(group.id)}
                              disabled={deleteGroup.isPending}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </TD>
                      </TR>
                    ))
                  ) : (
                    <TR>
                      <TD colSpan={5} className="h-32 text-center text-sm text-muted-foreground">
                        {isLoading ? "Loading copy groups..." : "No copy groups yet"}
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
