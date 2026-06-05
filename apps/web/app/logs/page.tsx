"use client";

import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/data-table";
import { Page } from "@/components/layout/page";
import { apiFetch } from "@/lib/api";

type AuditLog = {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export default function LogsPage() {
  const {data: logs = [], isLoading} = useQuery({
    queryKey: ["logs"],
    queryFn: () => apiFetch<AuditLog[]>("/logs")
  });
  const rows = logs.map((log) => ({
    action: log.action,
    entity: log.entity_type,
    entity_id: log.entity_id ?? "-",
    time: new Date(log.created_at).toLocaleString("en-IN")
  }));

  return (
    <Page title="Logs">
      <DataTable rows={rows} columns={["action", "entity", "entity_id", "time"]} emptyMessage={isLoading ? "Loading logs..." : "No audit logs yet"} />
    </Page>
  );
}
