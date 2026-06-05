"use client";

import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch, getAccessToken } from "@/lib/api";
import {
  extractSharekhanCallbackParams,
  forgetPendingSharekhanLogin,
  resolvePendingSharekhanLogin
} from "@/lib/sharekhan-login";

type CallbackStatus = "loading" | "success" | "error";

type TokenExchangeResponse = {
  ok: boolean;
  account_id: string;
  request_token_saved?: boolean;
  access_token_generated?: boolean;
  profile?: {
    access_token?: string | null;
    customer_id?: string | null;
    login_id?: string | null;
    full_name?: string | null;
    token_expires_at?: string | null;
  };
};

function statusIcon(status: CallbackStatus) {
  if (status === "success") return <CheckCircle2 className="h-5 w-5 text-emerald-400" />;
  if (status === "error") return <AlertTriangle className="h-5 w-5 text-destructive" />;
  return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />;
}

function CallbackContent() {
  const router = useRouter();
  const [status, setStatus] = useState<CallbackStatus>("loading");
  const [message, setMessage] = useState("Completing Sharekhan login...");
  const [tokenResult, setTokenResult] = useState<TokenExchangeResponse | null>(null);
  const [displayedAccount, setDisplayedAccount] = useState("Secure callback state");
  const [canReturnToAccounts, setCanReturnToAccounts] = useState(false);

  useEffect(() => {
    let active = true;

    async function exchangeToken() {
      const callbackParams = extractSharekhanCallbackParams(window.location.href);
      const pending = resolvePendingSharekhanLogin();
      const state = callbackParams.state ?? pending.login?.state ?? null;
      const accountId = pending.login?.accountId ?? callbackParams.accountId;
      const requestToken = callbackParams.requestToken;

      if (pending.login?.accountId || pending.login?.accountName) {
        setDisplayedAccount(pending.login.accountName ?? pending.login.accountId ?? "Secure callback state");
      } else if (accountId) {
        setDisplayedAccount(accountId);
      } else if (state && state.length < 80) {
        setDisplayedAccount(state);
      }

      if (!requestToken) {
        setStatus("error");
        const detected = callbackParams.detectedKeys.length ? callbackParams.detectedKeys.join(", ") : "none";
        setMessage(`Sharekhan did not return a request token. Detected URL fields: ${detected}.`);
        return;
      }

      if (!accountId && !state) {
        setStatus("error");
        setMessage("Sharekhan returned a request token, but this browser tab could not identify which account started login. Start account-wise login again from Accounts.");
        return;
      }

      try {
        setMessage("Saving Sharekhan request token...");
        const result = await apiFetch<TokenExchangeResponse>("/accounts/sharekhan/callback", {
          method: "POST",
          body: JSON.stringify({account_id: accountId, state: state ?? undefined, request_token: requestToken})
        });
        if (!active) return;
        setTokenResult(result);
        if (!result.ok) {
          setStatus("error");
          setMessage("Sharekhan returned a request token, but it was not stored.");
          return;
        }
        setStatus("success");
        const hasAppSession = Boolean(getAccessToken());
        setCanReturnToAccounts(hasAppSession);
        setMessage(
          hasAppSession
            ? "Sharekhan access token and profile saved. Returning to Accounts..."
            : "Sharekhan access token and profile saved. Return to your original Accounts tab."
        );
        forgetPendingSharekhanLogin(state, result.account_id);
        if (hasAppSession) {
          window.setTimeout(() => {
            router.replace("/accounts");
          }, 1500);
        }
      } catch (error) {
        if (!active) return;
        setStatus("error");
        setMessage(error instanceof Error ? error.message : "Sharekhan request token save failed.");
      }
    }

    void exchangeToken();
    return () => {
      active = false;
    };
  }, [router]);

  return (
    <main className="grid min-h-screen place-items-center bg-background px-4 py-10 text-foreground">
      <Card className="w-full max-w-lg">
        <CardContent className="grid gap-5 pt-5">
          <div className="flex items-start gap-3">
            <div className="mt-0.5">{statusIcon(status)}</div>
            <div className="grid gap-2">
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-semibold">Sharekhan Login</h1>
                <Badge>{status === "success" ? "CONNECTED" : status === "error" ? "FAILED" : "PENDING"}</Badge>
              </div>
              <p className="text-sm text-muted-foreground">{message}</p>
            </div>
          </div>

          <div className="grid gap-2 rounded-md border bg-muted/30 p-3 text-sm">
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">Account</span>
              <span className="truncate font-medium">{tokenResult?.account_id ?? displayedAccount}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">Customer</span>
              <span className="truncate font-medium">{tokenResult?.profile?.customer_id ?? "-"}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">Access token</span>
              <span className="truncate font-medium">{tokenResult?.access_token_generated ? "Saved" : "-"}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">Login ID</span>
              <span className="truncate font-medium">{tokenResult?.profile?.login_id ?? "-"}</span>
            </div>
          </div>

          <div className="flex justify-end gap-2">
            {canReturnToAccounts ? (
              <Button type="button" variant="outline" onClick={() => router.replace("/accounts")}>
                Accounts
              </Button>
            ) : status === "success" ? (
              <Button type="button" variant="outline" onClick={() => window.close()}>
                Close
              </Button>
            ) : null}
            {status === "error" ? (
              <Button onClick={() => window.location.reload()}>
                Retry
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </main>
  );
}

export default function SharekhanCallbackPage() {
  return (
    <Suspense
      fallback={
        <main className="grid min-h-screen place-items-center bg-background px-4 py-10 text-foreground">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </main>
      }
    >
      <CallbackContent />
    </Suspense>
  );
}
