"use client";

import { KeyRound, Landmark, Network, Save, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { Page } from "@/components/layout/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch, clearAccessToken, getAccessToken } from "@/lib/api";

function Field({label, className, children}: {label: string; className?: string; children: ReactNode}) {
  return (
    <label className={className}>
      <span className="mb-1.5 block text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

export default function NewAccountPage() {
  const router = useRouter();
  const [accountType, setAccountType] = useState<"MASTER" | "COPY">("COPY");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!getAccessToken()) {
      toast.error("Please sign in before saving accounts.");
      router.replace("/login");
      return;
    }
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(form.entries()) as Record<string, string>;
    for (const [key, value] of Object.entries(payload)) {
      const trimmed = value.trim();
      if (trimmed) payload[key] = trimmed;
      else delete payload[key];
    }
    const hasProxy = Boolean(payload.proxy_host || payload.proxy_port || payload.proxy_username || payload.proxy_password);
    if (!hasProxy) {
      delete payload.proxy_scheme;
      delete payload.proxy_host;
      delete payload.proxy_port;
      delete payload.proxy_username;
      delete payload.proxy_password;
    }
    try {
      await apiFetch("/accounts", {
        method: "POST",
        body: JSON.stringify({...payload, account_type: accountType})
      });
      toast.success("Account saved");
      router.push("/accounts");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearAccessToken();
        router.replace("/login");
      }
      toast.error(error instanceof Error ? error.message : "Account save failed");
    }
  }

  return (
    <Page title="New Account">
      <form className="grid max-w-6xl gap-4 lg:grid-cols-[1fr_360px]" onSubmit={submit}>
        <Card>
          <CardHeader className="border-b">
            <div className="flex items-center gap-2">
              <Landmark className="h-4 w-4 text-muted-foreground" />
              <CardTitle>Sharekhan Account</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="grid gap-6 pt-4">
            <section className="grid gap-3 sm:grid-cols-3">
              <Field label="Account name" className="sm:col-span-3">
                <Input name="account_name" placeholder="Primary account" required />
              </Field>
              <Field label="Customer ID">
                <Input name="customer_id" placeholder="Auto-filled after login" />
              </Field>
              <Field label="Channel user">
                <Input name="login_id" placeholder="Optional" />
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
            </section>

            <section className="grid gap-3 sm:grid-cols-2">
              <div className="flex items-center gap-2 sm:col-span-2">
                <KeyRound className="h-4 w-4 text-muted-foreground" />
                <h2 className="text-sm font-medium">API Credentials</h2>
              </div>
              <Field label="API key">
                <Input name="api_key" placeholder="API key" required />
              </Field>
              <Field label="Secure key">
                <Input name="secret_key" type="password" placeholder="Secure key" required />
              </Field>
              <Field label="Vendor key" className="sm:col-span-2">
                <Input name="vendor_key" placeholder="Optional" />
              </Field>
            </section>
          </CardContent>
        </Card>

        <div className="grid gap-4">
          <Card>
            <CardHeader className="border-b">
              <div className="flex items-center gap-2">
                <Network className="h-4 w-4 text-muted-foreground" />
                <CardTitle>Proxy</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="grid gap-3 pt-4">
              <div className="grid grid-cols-[96px_1fr] gap-3">
                <Field label="Scheme">
                  <select name="proxy_scheme" defaultValue="http" className="h-9 w-full rounded-md border bg-background px-3 text-sm outline-none transition focus:ring-2 focus:ring-ring">
                    <option value="http">HTTP</option>
                    <option value="https">HTTPS</option>
                  </select>
                </Field>
                <Field label="Host">
                  <Input name="proxy_host" placeholder="proxy.example.com" />
                </Field>
              </div>
              <Field label="Port">
                <Input name="proxy_port" type="number" min="1" max="65535" inputMode="numeric" placeholder="8080" />
              </Field>
              <Field label="ID / username">
                <Input name="proxy_username" placeholder="proxy-user" autoComplete="off" />
              </Field>
              <Field label="Password">
                <Input name="proxy_password" type="password" placeholder="Proxy password" autoComplete="new-password" />
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="border-b">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-muted-foreground" />
                <CardTitle>Save Account</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="pt-4">
              <Button type="submit" className="w-full">
                <Save className="h-4 w-4" />
                Save
              </Button>
            </CardContent>
          </Card>
        </div>
      </form>
    </Page>
  );
}
