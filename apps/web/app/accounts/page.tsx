"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Edit, ExternalLink, Loader2, LogIn, Plus, RefreshCw, Save, Trash2, X } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Page } from "@/components/layout/page";
import { apiFetch } from "@/lib/api";
import {
  extractStateFromLoginUrl,
  rememberPendingSharekhanLogin,
  rememberPendingSharekhanLoginInWindow
} from "@/lib/sharekhan-login";

type AccountType = "MASTER" | "COPY";

type BrokerAccount = {
  id: string;
  broker: string;
  account_name: string;
  customer_id: string | null;
  login_id: string | null;
  api_key: string;
  secret_key: string;
  vendor_key: string | null;
  proxy_scheme: "http" | "https" | null;
  proxy_host: string | null;
  proxy_port: number | null;
  proxy_username: string | null;
  proxy_password: string | null;
  request_token: string | null;
  access_token: string | null;
  refresh_token: string | null;
  token_expires_at: string | null;
  credentials_readable: boolean;
  account_type: AccountType;
  is_active: boolean;
  last_connected_at: string | null;
  created_at: string;
  updated_at: string;
};

type AccountPatch = Partial<{
  account_name: string;
  customer_id: string | null;
  login_id: string | null;
  api_key: string;
  secret_key: string;
  vendor_key: string | null;
  proxy_scheme: "http" | "https" | null;
  proxy_host: string | null;
  proxy_port: number | null;
  proxy_username: string | null;
  proxy_password: string | null;
  account_type: AccountType;
  is_active: boolean;
}>;

type LoginUrlResponse = {
  login_url: string;
  state?: string;
};

type LoginLink = {
  accountId: string;
  accountName: string;
  loginUrl: string;
  state: string | null;
  opened: boolean;
};

function Field({label, children}: {label: string; children: ReactNode}) {
  return (
    <label className="grid gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function cleanString(value: FormDataEntryValue | null) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed || null;
}

function connectionStatus(account: BrokerAccount) {
  if (!account.credentials_readable) return "CREDENTIALS_LOCKED";
  if (!account.is_active) return "INACTIVE";
  if (account.access_token) return "CONNECTED";
  if (account.request_token) return "TOKEN_SAVED";
  return "LOGIN_REQUIRED";
}

function formatDate(value: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function openBlankTab() {
  const popup = window.open("about:blank", "_blank");
  if (popup) popup.opener = null;
  return popup;
}

function proxyLabel(account: BrokerAccount) {
  if (!account.proxy_host) return "-";
  return `${account.proxy_scheme ?? "http"}://${account.proxy_host}:${account.proxy_port ?? ""}`;
}

function LoginLinksDrawer({
  links,
  onClose
}: {
  links: LoginLink[];
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-40 bg-black/60" onClick={onClose}>
      <aside
        className="absolute right-0 top-0 h-full w-full max-w-xl overflow-y-auto border-l bg-background shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex h-14 items-center justify-between border-b bg-background px-5">
          <div>
            <h2 className="text-base font-semibold">Sharekhan Login</h2>
            <p className="text-xs text-muted-foreground">{links.length} login {links.length === 1 ? "link" : "links"} prepared</p>
          </div>
          <Button variant="ghost" size="icon" title="Close" aria-label="Close" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="grid gap-3 p-5">
          {links.map((link) => (
            <Card key={link.accountId}>
              <CardContent className="flex items-center justify-between gap-3 pt-4">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{link.accountName}</div>
                  <div className="mt-1">
                    <Badge>{link.opened ? "OPEN" : "READY"}</Badge>
                  </div>
                </div>
                <Button
                  variant="outline"
                  onClick={() => {
                    const popup = openBlankTab();
                    if (link.state) {
                      rememberPendingSharekhanLoginInWindow(popup, {
                        state: link.state,
                        accountId: link.accountId,
                        accountName: link.accountName
                      });
                    }
                    if (popup) {
                      popup.location.href = link.loginUrl;
                    } else {
                      window.open(link.loginUrl, "_blank");
                    }
                  }}
                >
                  <ExternalLink className="h-4 w-4" />
                  Open
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </aside>
    </div>
  );
}

function AccountDrawer({
  account,
  saving,
  onClose,
  onSubmit
}: {
  account: BrokerAccount;
  saving: boolean;
  onClose: () => void;
  onSubmit: (payload: AccountPatch) => void;
}) {
  const [accountType, setAccountType] = useState<AccountType>(account.account_type);
  const [isActive, setIsActive] = useState(account.is_active);
  const [clearVendor, setClearVendor] = useState(false);
  const [clearProxy, setClearProxy] = useState(false);

  useEffect(() => {
    setAccountType(account.account_type);
    setIsActive(account.is_active);
    setClearVendor(false);
    setClearProxy(false);
  }, [account]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload: AccountPatch = {
      account_name: cleanString(form.get("account_name")) ?? account.account_name,
      customer_id: cleanString(form.get("customer_id")),
      login_id: cleanString(form.get("login_id")),
      account_type: accountType,
      is_active: isActive
    };
    const apiKey = cleanString(form.get("api_key"));
    const secureKey = cleanString(form.get("secret_key"));
    const vendorKey = cleanString(form.get("vendor_key"));
    if (apiKey) payload.api_key = apiKey;
    if (secureKey) payload.secret_key = secureKey;
    if (clearVendor) {
      payload.vendor_key = null;
    } else if (vendorKey !== null) {
      payload.vendor_key = vendorKey;
    }

    if (clearProxy) {
      payload.proxy_scheme = null;
      payload.proxy_host = null;
      payload.proxy_port = null;
      payload.proxy_username = null;
      payload.proxy_password = null;
    } else {
      const proxyHost = cleanString(form.get("proxy_host"));
      const proxyPort = cleanString(form.get("proxy_port"));
      const proxyUsername = cleanString(form.get("proxy_username"));
      const proxyPassword = cleanString(form.get("proxy_password"));
      if (proxyHost || proxyPort || proxyUsername || proxyPassword) {
        payload.proxy_scheme = (cleanString(form.get("proxy_scheme")) as "http" | "https" | null) ?? "http";
        payload.proxy_host = proxyHost;
        payload.proxy_port = proxyPort ? Number(proxyPort) : null;
        payload.proxy_username = proxyUsername;
        if (proxyPassword) payload.proxy_password = proxyPassword;
      }
    }
    onSubmit(payload);
  }

  return (
    <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose}>
      <aside
        className="absolute right-0 top-0 h-full w-full max-w-2xl overflow-y-auto border-l bg-background shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex h-14 items-center justify-between border-b bg-background px-5">
          <div>
            <h2 className="text-base font-semibold">Edit Account</h2>
            <p className="text-xs text-muted-foreground">{account.id}</p>
          </div>
          <Button variant="ghost" size="icon" title="Close" aria-label="Close" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <form className="grid gap-4 p-5" onSubmit={submit}>
          <Card>
            <CardContent className="grid gap-3 pt-4 sm:grid-cols-2">
              <Field label="Account name">
                <Input name="account_name" defaultValue={account.account_name} required />
              </Field>
              <Field label="Status">
                <button
                  type="button"
                  className="h-9 rounded-md border bg-background px-3 text-left text-sm"
                  onClick={() => setIsActive((value) => !value)}
                >
                  {isActive ? "Active" : "Inactive"}
                </button>
              </Field>
              <Field label="Customer ID">
                <Input name="customer_id" defaultValue={account.customer_id ?? ""} placeholder="Auto-filled after login" />
              </Field>
              <Field label="Channel user">
                <Input name="login_id" defaultValue={account.login_id ?? ""} placeholder="Optional" />
              </Field>
              <Field label="Account type">
                <div className="grid h-9 grid-cols-2 rounded-md border bg-muted p-1">
                  {(["MASTER", "COPY"] as const).map((value) => (
                    <button
                      key={value}
                      type="button"
                      className={
                        accountType === value
                          ? "rounded-sm bg-background text-xs font-medium shadow-sm"
                          : "rounded-sm text-xs font-medium text-muted-foreground"
                      }
                      onClick={() => setAccountType(value)}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              </Field>
              <Field label="Broker">
                <Input value={account.broker} disabled />
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="grid gap-3 pt-4 sm:grid-cols-2">
              <Field label="New API key">
                <Input name="api_key" placeholder="Leave blank to keep current" autoComplete="off" />
              </Field>
              <Field label="New Secure key">
                <Input name="secret_key" type="password" placeholder="Leave blank to keep current" autoComplete="new-password" />
              </Field>
              <Field label="New vendor key">
                <Input name="vendor_key" placeholder="Leave blank to keep current" autoComplete="off" disabled={clearVendor} />
              </Field>
              <Field label="Current API key">
                <Input value={account.api_key} disabled />
              </Field>
              <label className="flex items-center gap-2 text-sm sm:col-span-2">
                <input type="checkbox" className="h-4 w-4" checked={clearVendor} onChange={(event) => setClearVendor(event.target.checked)} />
                Clear vendor key
              </label>
              {!account.credentials_readable ? (
                <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive sm:col-span-2">
                  Stored account secrets cannot be decrypted with the current app secret. Enter the API key and Secure key again, and re-enter or clear optional vendor/proxy details.
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="grid gap-3 pt-4 sm:grid-cols-2">
              <label className="flex items-center gap-2 text-sm sm:col-span-2">
                <input type="checkbox" className="h-4 w-4" checked={clearProxy} onChange={(event) => setClearProxy(event.target.checked)} />
                Clear proxy details
              </label>
              <Field label="Scheme">
                <select
                  name="proxy_scheme"
                  defaultValue={account.proxy_scheme ?? "http"}
                  disabled={clearProxy}
                  className="h-9 rounded-md border bg-background px-3 text-sm"
                >
                  <option value="http">HTTP</option>
                  <option value="https">HTTPS</option>
                </select>
              </Field>
              <Field label="Host">
                <Input name="proxy_host" defaultValue={account.proxy_host ?? ""} disabled={clearProxy} />
              </Field>
              <Field label="Port">
                <Input name="proxy_port" type="number" min="1" max="65535" defaultValue={account.proxy_port ?? ""} disabled={clearProxy} />
              </Field>
              <Field label="ID / username">
                <Input name="proxy_username" defaultValue={account.proxy_username ?? ""} disabled={clearProxy} autoComplete="off" />
              </Field>
              <Field label="New proxy password">
                <Input name="proxy_password" type="password" placeholder="Leave blank to keep current" disabled={clearProxy} />
              </Field>
            </CardContent>
          </Card>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              <Save className="h-4 w-4" />
              {saving ? "Saving..." : "Save"}
            </Button>
          </div>
        </form>
      </aside>
    </div>
  );
}

function AccountProfilePanel({account}: {account: BrokerAccount}) {
  return (
    <div className="border-t bg-muted/20 px-4 py-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Field label="Customer ID">
          <div className="min-h-9 rounded-md border bg-background px-3 py-2 text-sm">{account.customer_id || "-"}</div>
        </Field>
        <Field label="Login ID">
          <div className="min-h-9 rounded-md border bg-background px-3 py-2 text-sm">{account.login_id || "-"}</div>
        </Field>
        <Field label="Broker">
          <div className="min-h-9 rounded-md border bg-background px-3 py-2 text-sm">{account.broker || "-"}</div>
        </Field>
        <Field label="Request token">
          <div className="min-h-9 rounded-md border bg-background px-3 py-2 text-sm">{account.request_token || "-"}</div>
        </Field>
        <Field label="Access token">
          <div className="min-h-9 rounded-md border bg-background px-3 py-2 text-sm">{account.access_token || "-"}</div>
        </Field>
        <Field label="Refresh token">
          <div className="min-h-9 rounded-md border bg-background px-3 py-2 text-sm">{account.refresh_token || "-"}</div>
        </Field>
        <Field label="Expires">
          <div className="min-h-9 rounded-md border bg-background px-3 py-2 text-sm">{formatDate(account.token_expires_at)}</div>
        </Field>
        <Field label="Last connected">
          <div className="min-h-9 rounded-md border bg-background px-3 py-2 text-sm">{formatDate(account.last_connected_at)}</div>
        </Field>
        <Field label="Credentials">
          <div className="min-h-9 rounded-md border bg-background px-3 py-2 text-sm">
            {account.credentials_readable ? "Readable" : "Credentials locked"}
          </div>
        </Field>
      </div>
    </div>
  );
}

export default function AccountsPage() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<BrokerAccount | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loginLinks, setLoginLinks] = useState<LoginLink[]>([]);
  const {data: accounts = [], isLoading, isError, refetch, isFetching} = useQuery({
    queryKey: ["accounts"],
    queryFn: () => apiFetch<BrokerAccount[]>("/accounts")
  });

  useEffect(() => {
    setSelectedIds((current) => {
      const accountIds = new Set(accounts.map((account) => account.id));
      return new Set([...current].filter((id) => accountIds.has(id)));
    });
  }, [accounts]);

  const updateAccount = useMutation({
    mutationFn: ({id, payload}: {id: string; payload: AccountPatch}) =>
      apiFetch<BrokerAccount>(`/accounts/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      }),
    onSuccess: () => {
      toast.success("Account updated");
      setEditing(null);
      void queryClient.invalidateQueries({queryKey: ["accounts"]});
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Account update failed")
  });

  const deleteAccount = useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/accounts/${id}`, {
        method: "DELETE"
      }),
    onSuccess: () => {
      toast.success("Account deleted");
      void queryClient.invalidateQueries({queryKey: ["accounts"]});
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Account delete failed")
  });

  function remove(account: BrokerAccount) {
    const ok = window.confirm(`Delete ${account.account_name}? This cannot be undone.`);
    if (ok) deleteAccount.mutate(account.id);
  }

  function toggleAccount(accountId: string, checked: boolean) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(accountId);
      } else {
        next.delete(accountId);
      }
      return next;
    });
  }

  function toggleAll(checked: boolean) {
    setSelectedIds(checked ? new Set(accounts.map((account) => account.id)) : new Set());
  }

  async function startLogin(targets: BrokerAccount[]) {
    if (!targets.length) {
      toast.error("No accounts available");
      return;
    }

    const popups = targets.map(() => openBlankTab());
    try {
      const links = await Promise.all(
        targets.map(async (account, index) => {
          const response = await apiFetch<LoginUrlResponse>(`/accounts/${account.id}/sharekhan/login-url`, {
            method: "POST"
          });
          const popup = popups[index];
          const state = response.state ?? extractStateFromLoginUrl(response.login_url);
          if (state) {
            const pendingLogin = {
              state,
              accountId: account.id,
              accountName: account.account_name
            };
            rememberPendingSharekhanLogin(pendingLogin);
            rememberPendingSharekhanLoginInWindow(popup, pendingLogin);
          }
          if (popup) popup.location.href = response.login_url;
          return {
            accountId: account.id,
            accountName: account.account_name,
            loginUrl: response.login_url,
            state,
            opened: Boolean(popup)
          };
        })
      );
      setLoginLinks(links);
      toast.success(targets.length === 1 ? "Sharekhan login opened" : "Sharekhan login links prepared");
    } catch (error) {
      popups.forEach((popup) => popup?.close());
      toast.error(error instanceof Error ? error.message : "Sharekhan login failed");
    }
  }

  const selectedAccounts = accounts.filter((account) => selectedIds.has(account.id));
  const centralLoginTargets = selectedAccounts.length ? selectedAccounts : accounts;
  const allSelected = accounts.length > 0 && selectedIds.size === accounts.length;

  return (
    <Page
      title="Accounts"
      actions={
        <div className="flex items-center gap-2">
          <Button disabled={!accounts.length} onClick={() => void startLogin(centralLoginTargets)}>
            <LogIn className="h-4 w-4" />
            {selectedIds.size ? `Login selected (${selectedIds.size})` : "Login all"}
          </Button>
          <Button variant="outline" size="icon" title="Refresh" aria-label="Refresh" onClick={() => void refetch()}>
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
          </Button>
          <Link
            href="/accounts/new"
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            Add
          </Link>
        </div>
      }
    >
      <div className="overflow-hidden rounded-lg border bg-card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-border bg-background"
              aria-label="Select all accounts"
              checked={allSelected}
              onChange={(event) => toggleAll(event.target.checked)}
            />
            Select all
          </label>
          <div className="text-xs text-muted-foreground">
            {accounts.length} {accounts.length === 1 ? "account" : "accounts"}
          </div>
        </div>

        {isLoading ? (
          <div className="flex h-32 items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading accounts...
          </div>
        ) : isError ? (
          <div className="flex h-32 items-center justify-center px-4 text-center text-sm text-destructive">
            Accounts could not be loaded.
          </div>
        ) : accounts.length ? (
          <div className="divide-y">
            {accounts.map((account) => {
              const isOpen = expandedId === account.id;
              return (
                <section key={account.id} className="bg-card">
                  <div className="grid gap-3 px-4 py-4 lg:grid-cols-[auto_minmax(0,1.4fr)_auto_auto] xl:grid-cols-[auto_minmax(0,1.4fr)_auto_auto_auto_auto] xl:items-center">
                    <input
                      type="checkbox"
                      className="mt-2 h-4 w-4 rounded border-border bg-background lg:mt-3 xl:mt-0"
                      aria-label={`Select ${account.account_name}`}
                      checked={selectedIds.has(account.id)}
                      onChange={(event) => toggleAccount(account.id, event.target.checked)}
                    />

                    <button
                      type="button"
                      className="flex min-w-0 items-start gap-3 rounded-md text-left transition-colors hover:text-foreground"
                      aria-expanded={isOpen}
                      onClick={() => setExpandedId(isOpen ? null : account.id)}
                    >
                      <ChevronDown className={`mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform ${isOpen ? "rotate-180" : ""}`} />
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold">{account.account_name}</span>
                        <span className="mt-1 block truncate text-xs text-muted-foreground">{account.broker} - {account.id}</span>
                      </span>
                    </button>

                    <div className="flex flex-wrap items-center gap-2">
                      <Badge>{account.account_type}</Badge>
                      <Badge>{connectionStatus(account)}</Badge>
                    </div>

                    <div className="grid gap-1 text-sm">
                      <span className="text-xs text-muted-foreground">Customer</span>
                      <span className="truncate">{account.customer_id || "-"}</span>
                    </div>

                    <div className="grid gap-1 text-sm">
                      <span className="text-xs text-muted-foreground">Proxy</span>
                      <span className="max-w-56 truncate">{proxyLabel(account)}</span>
                    </div>

                    <div className="flex items-center justify-between gap-3 xl:justify-end">
                      <div className="grid gap-1 text-sm xl:text-right">
                        <span className="text-xs text-muted-foreground">Updated</span>
                        <span>{formatDate(account.updated_at)}</span>
                      </div>
                      <div className="flex shrink-0 justify-end gap-1">
                        <Button variant="ghost" size="icon" title="Login" aria-label="Login" onClick={() => void startLogin([account])}>
                          <LogIn className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" title="Edit" aria-label="Edit" onClick={() => setEditing(account)}>
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Delete"
                          aria-label="Delete"
                          disabled={deleteAccount.isPending}
                          onClick={() => remove(account)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  </div>

                  {isOpen ? <AccountProfilePanel account={account} /> : null}
                </section>
              );
            })}
          </div>
        ) : (
          <div className="flex h-32 items-center justify-center px-4 text-center text-sm text-muted-foreground">
            No accounts yet. Add a Sharekhan account to begin.
          </div>
        )}
      </div>

      {editing ? (
        <AccountDrawer
          account={editing}
          saving={updateAccount.isPending}
          onClose={() => setEditing(null)}
          onSubmit={(payload) => updateAccount.mutate({id: editing.id, payload})}
        />
      ) : null}
      {loginLinks.length ? <LoginLinksDrawer links={loginLinks} onClose={() => setLoginLinks([])} /> : null}
    </Page>
  );
}
