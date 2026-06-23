import { useState } from "react"
import { ChevronDownIcon } from "lucide-react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible"
import { PosterThumb } from "@/features/list-syncarr/components/poster-thumb"
import { StatusBadge } from "@/features/list-syncarr/components/status-badge"
import { cn } from "@/shared/lib/utils"
import { useLists, useListItems } from "@/shared/lib/queries"
import {
  displayTitle,
  formatNextSync,
  formatRelativeTime,
} from "@/shared/lib/format"
import type { ListSummary } from "@/shared/lib/api"

/** One collapsible synced-list row; its items load lazily on first expand. */
function ListRow({ list }: { list: ListSummary }) {
  const [open, setOpen] = useState(false)
  const { data: items, isLoading } = useListItems(list.slug, open)

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="py-3 first:pt-0 last:pb-0"
    >
      <CollapsibleTrigger className="flex w-full items-center gap-3 text-left">
        <ChevronDownIcon
          className={cn(
            "size-4 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
        <span className="flex-1 text-sm font-medium">
          {list.name}{" "}
          <span className="text-muted-foreground">({list.item_count})</span>
        </span>
        <span className="hidden text-xs text-muted-foreground sm:inline">
          last synced:{" "}
          {list.last_synced_at
            ? formatRelativeTime(list.last_synced_at)
            : "never"}
        </span>
        <span className="text-xs text-muted-foreground">
          next sync {formatNextSync(list.next_sync_at)}
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        {isLoading ? (
          <p className="px-7 py-3 text-sm text-muted-foreground">
            Loading items…
          </p>
        ) : (items?.length ?? 0) === 0 ? (
          <p className="px-7 py-3 text-sm text-muted-foreground">
            This list has no items yet.
          </p>
        ) : (
          <ul className="grid grid-cols-3 gap-4 px-7 py-3 sm:grid-cols-4 md:grid-cols-6">
            {items?.map((item) => (
              <li
                key={`${item.list_id}:${item.trakt_id}`}
                className="flex flex-col gap-1.5"
              >
                <PosterThumb item={item} />
                <span
                  className="truncate text-xs font-medium"
                  title={displayTitle(item.title)}
                >
                  {displayTitle(item.title)}
                </span>
                <StatusBadge status={item.status} />
              </li>
            ))}
          </ul>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}

/** Collapsible view of the Trakt lists selected for syncing. */
export function Lists() {
  const { data: lists, isLoading } = useLists()

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Lists</h1>
        <p className="text-sm text-muted-foreground">
          Trakt lists kept in sync by the engine.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Synced lists</CardTitle>
          <CardDescription>Manage these from Settings → Trakt.</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading lists…</p>
          ) : (lists?.length ?? 0) === 0 ? (
            <p className="text-sm text-muted-foreground">
              No lists selected yet.
            </p>
          ) : (
            <ul className="divide-y">
              {lists?.map((list) => (
                <li key={`${list.owner_user}:${list.slug}`}>
                  <ListRow list={list} />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
