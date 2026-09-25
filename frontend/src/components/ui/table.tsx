import * as React from "react";

import { cn } from "@/lib/utils";

export const TableViewport = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "w-full overflow-x-auto overscroll-x-contain rounded-xl border border-border bg-card",
      className,
    )}
    {...props}
  />
));
TableViewport.displayName = "TableViewport";

export const Table = React.forwardRef<
  HTMLTableElement,
  React.TableHTMLAttributes<HTMLTableElement>
>(({ className, ...props }, ref) => (
  <table
    ref={ref}
    className={cn("w-full text-sm", className)}
    {...props}
  />
));
Table.displayName = "Table";
