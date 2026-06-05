import type React from "react";

import { cn } from "@/lib/utils";

const tones: Record<string, string> = {
  ACTIVE: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  CONNECTED: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  LIVE: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  READY: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  SENT: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  RUNNING: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  PLACED: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  TOKEN_SAVED: "border-zinc-500/30 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300",
  ENCRYPTED: "border-zinc-500/30 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300",
  LOGIN_REQUIRED: "border-zinc-500/30 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300",
  INACTIVE: "border-muted-foreground/30 bg-muted text-muted-foreground",
  DISCONNECTED: "border-muted-foreground/30 bg-muted text-muted-foreground",
  PAPER: "border-zinc-500/30 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300",
  PENDING: "border-zinc-500/30 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300",
  PAUSED: "border-zinc-500/30 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300",
  STOPPED: "border-muted-foreground/30 bg-muted text-muted-foreground",
  SKIPPED: "border-zinc-500/30 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300",
  PARTIAL: "border-secondary/40 bg-secondary/15 text-secondary-foreground dark:text-secondary",
  ERROR: "border-destructive/30 bg-destructive/10 text-destructive",
  SUCCESS: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  CREDENTIALS_LOCKED: "border-destructive/30 bg-destructive/10 text-destructive",
  MASTER: "border-accent/30 bg-accent/10 text-accent",
  COPY: "border-secondary/40 bg-secondary/15 text-secondary-foreground dark:text-secondary",
  FAILED: "border-destructive/30 bg-destructive/10 text-destructive",
  DEGRADED: "border-secondary/40 bg-secondary/15 text-secondary-foreground dark:text-secondary",
  OPEN: "border-accent/30 bg-accent/10 text-accent",
  AUDITED: "border-muted-foreground/30 bg-muted text-muted-foreground"
};

export function Badge({children, className}: {children: React.ReactNode; className?: string}) {
  const text = typeof children === "string" ? children : "";
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center rounded-sm border px-2 text-xs font-medium",
        tones[text] ?? "border-muted-foreground/30 bg-muted text-muted-foreground",
        className
      )}
    >
      {children}
    </span>
  );
}
