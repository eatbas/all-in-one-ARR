import { useEffect, useState } from "react"
import {
  ChevronDownIcon,
  ExternalLinkIcon,
  RefreshCwIcon,
  Trash2Icon,
} from "lucide-react"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/components/ui/alert-dialog"
import { Button } from "@/shared/components/ui/button"
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
import { Switch } from "@/shared/components/ui/switch"
import { PosterThumb } from "@/features/list-syncarr/components/poster-thumb"
import { StatusBadge } from "@/features/list-syncarr/components/status-badge"
import { cn } from "@/shared/lib/utils"
import {
  useLists,
  useListItems,
  useRemoveAvailable,
  useRemoveItem,
  useServiceSettings,
  useSyncNow,
} from "@/shared/lib/queries"
import {
  displayTitle,
  formatNextSync,
  formatRelativeTime,
  formatYear,
} from "@/shared/lib/format"
import { seerMediaUrl } from "@/shared/lib/api"
import type { Item, ListSummary } from "@/shared/lib/api"

/**
 * A `Date` that advances once per second, letting relative-time labels (the
 * next-sync countdown, "last synced" text) tick live without a page refresh.
 */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return now
}

/** One collapsible synced-list row; its items load lazily on first expand. */
function ListRow({
  list,
  seerUrl,
  showRemoved,
  now,
  onDelete,
}: {
  list: ListSummary
  /** Seer base URL, when configured, used to deep-link each item's request page. */
  seerUrl?: string
  /** Whether to include already-removed items in the rendered grid. */
  showRemoved: boolean
  /** The current time, ticked once per second so the sync labels count down live. */
  now: Date
  /** Remove a single item from its Trakt list (already user-confirmed). */
  onDelete: (item: Item) => void
}) {
  const [open, setOpen] = useState(false)
  const { data: items, isLoading } = useListItems(list.slug, open)
  // Removed items are hidden by default; the "Show removed" toggle reveals them.
  const visibleItems = showRemoved
    ? items
    : items?.filter((item) => item.status !== "removed")
  // The header count mirrors the toggle: active-only by default, and
  // "active + removed" (e.g. "0 + 6") once removed items are revealed.
  const removedCount = list.removed_count
  const activeCount = list.item_count - removedCount

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex min-h-14 w-full items-center gap-3 rounded-md px-2 py-4 text-left transition-colors hover:bg-muted/50">
        <ChevronDownIcon
          className={cn(
            "size-5 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
        <span className="flex-1 text-base font-medium">
          {list.name}{" "}
          <span className="text-muted-foreground">
            {showRemoved ? `(${activeCount} + ${removedCount})` : `(${activeCount})`}
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
      </CollapsibleTrigger>
      <CollapsibleContent>
        {isLoading ? (
          <p className="px-7 py-3 text-sm text-muted-foreground">
            Loading items…
          </p>
        ) : (visibleItems?.length ?? 0) === 0 ? (
          <p className="px-7 py-3 text-sm text-muted-foreground">
            This list has no items yet.
          </p>
        ) : (
          <ul className="grid grid-cols-3 gap-4 px-7 py-3 sm:grid-cols-4 md:grid-cols-5">
            {visibleItems?.map((item) => (
              <li
                key={`${item.list_id}:${item.trakt_id}`}
                className="flex flex-col gap-1"
              >
                {/* Poster overlays: a per-item delete control top-left, the
                    Seer request link top-right, the status pill bottom-right. */}
                <div className="relative">
                  <PosterThumb item={item} />
                  {/* Already-removed items are no longer on the Trakt list, so they
                      offer no delete control. */}
                  {item.status !== "removed" ? (
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <button
                          type="button"
                          title={`Remove "${displayTitle(item.title)}" from the list`}
                          aria-label={`Remove "${displayTitle(item.title)}" from the list`}
                          className="absolute left-1 top-1 inline-flex items-center justify-center rounded-md bg-background/85 p-1 text-muted-foreground shadow-sm backdrop-blur-sm transition-colors hover:text-destructive"
                        >
                          <Trash2Icon className="size-4" />
                        </button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>
                            Remove "{displayTitle(item.title)}"?
                          </AlertDialogTitle>
                          <AlertDialogDescription>
                            It will be removed from its Trakt list.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction onClick={() => onDelete(item)}>
                            Remove
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  ) : null}
                  {seerUrl && item.tmdb !== null ? (
                    <a
                      href={seerMediaUrl(seerUrl, item.type, item.tmdb)}
                      target="_blank"
                      rel="noreferrer noopener"
                      title={`Request "${displayTitle(item.title)}" in Seer`}
                      aria-label={`Request "${displayTitle(item.title)}" in Seer`}
                      className="absolute right-1 top-1 inline-flex items-center justify-center rounded-md bg-background/85 p-1 text-muted-foreground shadow-sm backdrop-blur-sm transition-colors hover:text-foreground"
                    >
                      <ExternalLinkIcon className="size-4" />
                    </a>
                  ) : null}
                  <StatusBadge
                    status={item.status}
                    className="absolute right-1 bottom-1 bg-background/85 shadow-sm backdrop-blur-sm"
                  />
                </div>
                <span
                  className="truncate text-xs font-medium"
                  title={displayTitle(item.title)}
                >
                  {displayTitle(item.title)}
                </span>
                {/* Year and media type on one row beneath the poster. */}
                <span className="truncate text-xs capitalize text-muted-foreground">
                  {formatYear(item.year)} · {item.type}
                </span>
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
  const { data: services } = useServiceSettings()
  const seerUrl = services?.seer.url
  const removeItem = useRemoveItem()
  const removeAvailable = useRemoveAvailable()
  const syncNow = useSyncNow()
  const now = useNow()
  const [showRemoved, setShowRemoved] = useState(false)

  function handleSync() {
    syncNow.mutate()
  }

  function handleDelete(item: Item) {
    removeItem.mutate({ list_id: item.list_id, trakt_id: item.trakt_id })
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Lists</h1>
        <p className="text-sm text-muted-foreground">
          Trakt lists kept in sync by the engine.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
          <div>
            <CardTitle>Synced lists</CardTitle>
            <CardDescription>
              Manage these from the Settings tab.
            </CardDescription>
          </div>
          <div className="flex items-center gap-4">
            <Button
              size="sm"
              onClick={handleSync}
              disabled={syncNow.isPending}
            >
              {/* The icon spins while a sync is in flight so the disabled state
                  reads as "working" rather than simply inert. */}
              <RefreshCwIcon
                className={cn("size-4", syncNow.isPending && "animate-spin")}
              />
              Sync now
            </Button>
            <div className="flex items-center gap-2">
              <Switch
                aria-label="Show removed items"
                checked={showRemoved}
                onCheckedChange={setShowRemoved}
              />
              <span className="text-sm text-muted-foreground">Show removed</span>
            </div>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={removeAvailable.isPending}
                >
                  <Trash2Icon className="size-4" />
                  Delete availables
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete available items?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This removes every item Seer reports as available from
                    its Trakt list.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={() => removeAvailable.mutate()}>
                    Delete
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
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
                  <ListRow
                    list={list}
                    seerUrl={seerUrl}
                    showRemoved={showRemoved}
                    now={now}
                    onDelete={handleDelete}
                  />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
