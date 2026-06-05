import type React from "react";

import { cn } from "@/lib/utils";

export function Card({className, ...props}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("min-w-0 overflow-hidden rounded-lg border bg-card text-card-foreground", className)} {...props} />;
}

export function CardHeader({className, ...props}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex min-w-0 items-center justify-between gap-3 p-4", className)} {...props} />;
}

export function CardTitle({className, ...props}: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("min-w-0 text-sm font-medium text-muted-foreground", className)} {...props} />;
}

export function CardContent({className, ...props}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("min-w-0 p-4 pt-0", className)} {...props} />;
}
