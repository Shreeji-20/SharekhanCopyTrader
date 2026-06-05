import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";

export function Page({title, actions, children}: {title: string; actions?: ReactNode; children: ReactNode}) {
  return (
    <AppShell>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-normal">{title}</h1>
        {actions}
      </div>
      {children}
    </AppShell>
  );
}
