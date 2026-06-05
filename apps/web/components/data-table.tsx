"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Search, SlidersHorizontal, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type Row = Record<string, string | number | boolean | null | undefined>;

export function DataTable({
  rows,
  columns,
  emptyMessage = "No records found"
}: {
  rows: Row[];
  columns: string[];
  emptyMessage?: string;
}) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [page, setPage] = useState(0);
  const [active, setActive] = useState<Row | null>(null);
  const pageSize = 8;
  const statuses = useMemo(() => {
    const values = rows.map((row) => String(row.status ?? "")).filter(Boolean);
    return ["ALL", ...Array.from(new Set(values))];
  }, [rows]);
  const filtered = rows.filter((row) => {
    const haystack = Object.values(row).join(" ").toLowerCase();
    const matchesQuery = haystack.includes(query.toLowerCase());
    const matchesStatus = status === "ALL" || String(row.status) === status;
    return matchesQuery && matchesStatus;
  });
  const paged = filtered.slice(page * pageSize, page * pageSize + pageSize);
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));

  return (
    <div className="rounded-lg border bg-card">
      <div className="flex flex-wrap items-center gap-2 border-b p-3">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input value={query} onChange={(event) => setQuery(event.target.value)} className="pl-9" placeholder="Search" />
        </div>
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(0);
            }}
            className="h-9 rounded-md border bg-background px-3 text-sm"
          >
            {statuses.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <THead>
            <TR>
              {columns.map((column) => (
                <TH key={column}>{column}</TH>
              ))}
              <TH className="w-12" />
            </TR>
          </THead>
          <TBody>
            {paged.length ? (
              paged.map((row, index) => (
                <TR key={index}>
                  {columns.map((column) => {
                    const value = row[column];
                    return (
                      <TD key={column}>
                        {column === "status" || column === "type" ? <Badge>{String(value)}</Badge> : String(value ?? "")}
                      </TD>
                    );
                  })}
                  <TD>
                    <Button variant="ghost" size="sm" onClick={() => setActive(row)}>
                      View
                    </Button>
                  </TD>
                </TR>
              ))
            ) : (
              <TR>
                <TD colSpan={columns.length + 1} className="h-32 text-center text-sm text-muted-foreground">
                  {emptyMessage}
                </TD>
              </TR>
            )}
          </TBody>
        </Table>
      </div>
      <div className="flex items-center justify-between border-t p-3 text-sm text-muted-foreground">
        <span>{filtered.length} rows</span>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" title="Previous page" aria-label="Previous page" onClick={() => setPage(Math.max(0, page - 1))}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span>
            {page + 1}/{totalPages}
          </span>
          <Button
            variant="outline"
            size="icon"
            title="Next page"
            aria-label="Next page"
            onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
      {active ? (
        <div className="fixed inset-0 z-40 bg-black/30" onClick={() => setActive(null)}>
          <aside
            className="absolute right-0 top-0 h-full w-full max-w-md overflow-y-auto border-l bg-background p-5 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Details</h2>
              <Button variant="ghost" size="icon" title="Close" aria-label="Close" onClick={() => setActive(null)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <dl className="grid gap-3">
              {Object.entries(active).map(([key, value]) => (
                <div key={key} className="grid gap-1 rounded-md border p-3">
                  <dt className="text-xs uppercase text-muted-foreground">{key}</dt>
                  <dd className="break-words text-sm">{String(value ?? "")}</dd>
                </div>
              ))}
            </dl>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
