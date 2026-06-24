import { Badge } from "@/shared/components/ui/badge"
import { cn } from "@/shared/lib/utils"
import type { ItemStatus } from "@/shared/lib/api"

/** Per-status badge styling so states are distinguishable at a glance. */
const STATUS_STYLES: Record<ItemStatus, string> = {
  synced: "border-sky-500/40 text-sky-600 dark:text-sky-400",
  requested: "border-amber-500/40 text-amber-600 dark:text-amber-400",
  available: "border-emerald-500/40 text-emerald-600 dark:text-emerald-400",
  removed: "border-muted-foreground/30 text-muted-foreground",
}

/** Abbreviated per-status labels so the pill stays compact in tight layouts. */
const STATUS_LABELS: Record<ItemStatus, string> = {
  synced: "Sync.",
  requested: "Req.",
  available: "Avail.",
  removed: "Rem.",
}

/** Outline badge rendering an item's lifecycle status, shared across views. */
export function StatusBadge({
  status,
  abbreviated = true,
  className,
}: {
  status: ItemStatus
  /** Render the abbreviated label (default) or the full capitalised word. */
  abbreviated?: boolean
  className?: string
}) {
  // The full word doubles as the title so the abbreviated pill stays accessible
  // on hover and to assistive technology.
  const fullLabel = status[0].toUpperCase() + status.slice(1)
  return (
    <Badge
      variant="outline"
      title={fullLabel}
      className={cn(STATUS_STYLES[status], className)}
    >
      {abbreviated ? STATUS_LABELS[status] : fullLabel}
    </Badge>
  )
}
