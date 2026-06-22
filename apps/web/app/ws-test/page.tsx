"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Page } from "@/components/layout/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const DEFAULT_WS_PATH = "/ws/live";

function formatMessage(message: string | Record<string, unknown>): string {
  if (typeof message === "string") return message;
  try {
    return JSON.stringify(message, null, 2);
  } catch {
    return String(message);
  }
}

export default function WebsocketTestPage() {
  const [status, setStatus] = useState("DISCONNECTED");
  const [logs, setLogs] = useState<string[]>([]);
  const [lastError, setLastError] = useState<string | null>(null);
  const [url, setUrl] = useState<string>(
    `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}${DEFAULT_WS_PATH}`
  );
  const wsRef = useRef<WebSocket | null>(null);

  const canConnect = status === "DISCONNECTED";
  const canDisconnect = status === "CONNECTED" || status === "CONNECTING";

  const origin = useMemo(() => {
    if (typeof window === "undefined") return "";
    return window.location.origin;
  }, []);

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const appendLog = (entry: string) => {
    setLogs((existing) => [entry, ...existing].slice(0, 100));
  };

  const connect = () => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setLastError(null);
    setStatus("CONNECTING");
    appendLog(`Connecting to ${url}`);

    const websocket = new WebSocket(url);
    wsRef.current = websocket;

    websocket.onopen = () => {
      setStatus("CONNECTED");
      appendLog("WebSocket opened");
    };

    websocket.onmessage = (event) => {
      let data = event.data;
      try {
        data = JSON.parse(data);
      } catch {
        // keep as text
      }
      appendLog(`Received message:\n${formatMessage(data)}`);
    };

    websocket.onerror = () => {
      setLastError("WebSocket error occurred.");
      appendLog("WebSocket error");
    };

    websocket.onclose = (event) => {
      wsRef.current = null;
      setStatus("DISCONNECTED");
      appendLog(`WebSocket closed (code=${event.code} reason=${event.reason})`);
    };
  };

  const disconnect = () => {
    if (!wsRef.current) return;
    appendLog("Closing WebSocket...");
    wsRef.current.close();
    wsRef.current = null;
    setStatus("DISCONNECTED");
  };

  const clearLogs = () => {
    setLogs([]);
    setLastError(null);
  };

  return (
    <Page title="WebSocket Test">
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card>
          <CardHeader>
            <CardTitle>Connection</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <div className="grid gap-2">
              <label className="text-sm font-medium">WebSocket URL</label>
              <input
                className="rounded-md border border-slate-200 bg-background px-3 py-2 text-sm outline-none transition focus:border-primary"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder={`${origin}${DEFAULT_WS_PATH}`}
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={connect} disabled={!canConnect}>
                Connect
              </Button>
              <Button variant="secondary" onClick={disconnect} disabled={!canDisconnect}>
                Disconnect
              </Button>
              <Button variant="outline" onClick={clearLogs}>
                Clear logs
              </Button>
            </div>
            <div className="rounded-md border border-slate-200 bg-muted p-3 text-sm">
              <p>Status: <strong>{status}</strong></p>
              {lastError ? <p className="text-destructive">Error: {lastError}</p> : null}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Notes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-6">
            <p>
              This page is a temporary WebSocket tester. If you want to remove it later, delete the <code>apps/web/app/ws-test</code> folder.
            </p>
            <p>
              Use it to verify the live WebSocket endpoint at <code>/ws/live</code> or any other URL.
            </p>
            <p>
              Messages will appear in the log panel below. The page does not persist data.
            </p>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Logs</CardTitle>
        </CardHeader>
        <CardContent className="max-h-[450px] overflow-auto bg-black/5 p-3 text-xs font-mono">
          {logs.length === 0 ? (
            <p className="text-muted-foreground">No log entries yet.</p>
          ) : (
            logs.map((line, index) => (
              <pre key={index} className="whitespace-pre-wrap break-words text-sm">
                {line}
              </pre>
            ))
          )}
        </CardContent>
      </Card>
    </Page>
  );
}
