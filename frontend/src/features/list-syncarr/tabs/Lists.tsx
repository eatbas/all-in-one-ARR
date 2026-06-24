import { useState } from "react"
import { ChevronDownIcon, ExternalLinkIcon, Trash2Icon } from "lucide-react"

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
import { PosterThumb } from "@/features/list-syncarr/components/poster-thumb"
import { StatusBadge } from "@/features/list-syncarr/components/status-badge"
import { cn } from "@/shared/lib/utils"
import {
  useLists,
  useListItems,
  useRemoveAvailable,
  useRemoveItem,
  useServiceSettings,
} from "@/shared/lib/queries"
import {
  displayTitle,
  formatNextSync,
  formatRelativeTime,
  formatYear,
} from "@/shared/lib/format"
import { jellyseerrMediaUrl } from "@/shared/lib/api"
import type { Item, ListSummary } from "@/shared/lib/api"

/** One collapsible synced-list row; its items load lazily on first expand. */
function ListRow({
  list,
  jellyseerrUrl,
  onDelete,
}: {
  list: ListSummary
  /** Jellyseerr base URL, when configured, used to deep-link each item's request page. */
  jellyseerrUrl?: string
  /** Remove a single item from its Trakt list (already user-confirmed). */
  onDelete: (item: Item) => void
}) {
  const [open, setOpen] = useState(false)
  const { data: items, isLoading } = useListItems(list.slug, open)

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
          <ul className="grid grid-cols-3 gap-4 px-7 py-3 sm:grid-cols-4 md:grid-cols-5">
            {items?.map((item) => (
              <li
                key={`${item.list_id}:${item.trakt_id}`}
                className="flex flex-col gap-1"
              >
                {/* Poster overlays: a per-item delete control top-left, the
                    Jellyseerr request link top-right, the status pill bottom-right. */}
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
                            It will be removed from its Trakt list. With dry-run on,
                            the removal is only logged, not sent to Trakt.
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
                  {jellyseerrUrl && item.tmdb !== null ? (
                    <a
                      href={jellyseerrMediaUrl(jellyseerrUrl, item.type, item.tmdb)}
                      target="_blank"
                      rel="noreferrer noopener"
                      title={`Request "${displayTitle(item.title)}" in Jellyseerr`}
                      aria-label={`Request "${displayTitle(item.title)}" in Jellyseerr`}
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
  const jellyseerrUrl = services?.jellyseerr.url
  const removeItem = useRemoveItem()
  const removeAvailable = useRemoveAvailable()

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
                  This removes every item Jellyseerr reports as available from its
                  Trakt list. With dry-run on, the removals are only logged, not
                  sent to Trakt.
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
                    jellyseerrUrl={jellyseerrUrl}
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
