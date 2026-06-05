import type React from "react";

import { cn } from "@/lib/utils";

export function Table({className, ...props}: React.HTMLAttributes<HTMLTableElement>) {
  return <table className={cn("w-full caption-bottom text-sm", className)} {...props} />;
}

export function THead({className, ...props}: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("border-b bg-muted/50", className)} {...props} />;
}

export function TBody({className, ...props}: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("divide-y", className)} {...props} />;
}

export function TR({className, ...props}: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("transition-colors hover:bg-muted/40", className)} {...props} />;
}

export function TH({className, ...props}: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return <th className={cn("h-10 px-3 text-left text-xs font-medium uppercase text-muted-foreground", className)} {...props} />;
}

export function TD({className, ...props}: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("h-11 px-3 align-middle", className)} {...props} />;
}
