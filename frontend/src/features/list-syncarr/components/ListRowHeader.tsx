import { ChevronDownIcon } from "lucide-react"

import { cn } from "@/shared/lib/utils"
import { formatNextSync, formatRelativeTime } from "@/shared/lib/format"
import type { ListSummary } from "@/shared/lib/api"

interface ListRowHeaderProps {
  list: ListSummary
  open: boolean
  showRemoved: boolean
  now: Date
}

/** Collapsible list-row trigger: name, counts, and sync timing. */
export function ListRowHeader({
  list,
  open,
  showRemoved,
  now,
}: ListRowHeaderProps) {
  const removedCount = list.removed_count
  const activeCount = list.item_count - removedCount

  return (
    <>
      <ChevronDownIcon
        className={cn(
          "size-5 shrink-0 text-muted-foreground transition-transform",
          open && "rotate-180",
        )}
      />
      <span className="flex-1 text-base font-medium">
        {list.name}{" "}
        <span className="text-muted-foreground">
          {showRemoved
            ? `(${activeCount} + ${removedCount})`
            : `(${activeCount})`}
        </span>
      </span>
      <span className="hidden text-xs text-muted-foreground sm:inline">
        last synced:{" "}
        {list.last_synced_at
          ? formatRelativeTime(list.last_synced_at, now)
          : "never"}
      </span>
      <span className="text-xs text-muted-foreground">
        next sync {formatNextSync(list.next_sync_at, now)}
      </span>
    </>
  )
}
