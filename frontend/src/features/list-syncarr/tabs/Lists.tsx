import { useState } from "react"

import {
  GRID_COLS,
  readStoredDensity,
  writeStoredDensity,
} from "@/shared/components/poster-grid/poster-grid-density"
import type { PosterDensity } from "@/shared/components/poster-grid/poster-grid-density"
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
import { ListItemCard } from "@/features/list-syncarr/components/ListItemCard"
import { ListRowHeader } from "@/features/list-syncarr/components/ListRowHeader"
import { ListsToolbar } from "@/features/list-syncarr/components/ListsToolbar"
import { SyncStats } from "@/features/list-syncarr/components/sync-stats"
import {
  useLists,
  useListItems,
  useRemoveAvailable,
  useRemoveItem,
  useServiceSettings,
  useSyncNow,
} from "@/shared/lib/queries"
import type { Item, ListSummary } from "@/shared/lib/api"
import { useVisibleItems } from "@/features/list-syncarr/tabs/useVisibleItems"
import { useNow } from "@/features/list-syncarr/tabs/useNow"
import {
  DEFAULT_LIST_SYNCARR_PER_ROW,
  LIST_SYNCARR_PER_ROW_STORAGE_KEY,
} from "@/features/list-syncarr/list-syncarr-tab"

/** One collapsible synced-list row; its items load lazily on first expand. */
function ListRow({
  list,
  seerUrl,
  showRemoved,
  density,
  now,
  onDelete,
}: {
  list: ListSummary
  /** Seer base URL, when configured, used to deep-link each item's request page. */
  seerUrl?: string
  /** Whether to include already-removed items in the rendered grid. */
  showRemoved: boolean
  /** Posters-per-row density for the grid and every overlay pill. */
  density: PosterDensity
  /** The current time, ticked once per second so the sync labels count down live. */
  now: Date
  /** Remove a single item from its Trakt list (already user-confirmed). */
  onDelete: (item: Item) => void
}) {
  const [open, setOpen] = useState(false)
  const { data: items, isLoading } = useListItems(list.slug, open)
  const visibleItems = useVisibleItems(items, showRemoved)

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex min-h-14 w-full items-center gap-3 rounded-md px-2 py-4 text-left transition-colors hover:bg-muted/50">
        <ListRowHeader
          list={list}
          open={open}
          showRemoved={showRemoved}
          now={now}
        />
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
          <div className="px-7 py-3">
            <ul data-testid="list-syncarr-grid" className={GRID_COLS[density]}>
              {visibleItems?.map((item) => (
                <ListItemCard
                  key={`${item.list_id}:${item.trakt_id}`}
                  item={item}
                  seerUrl={seerUrl}
                  density={density}
                  onDelete={onDelete}
                />
              ))}
            </ul>
          </div>
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
  const [density, setDensity] = useState<PosterDensity>(() =>
    readStoredDensity(
      LIST_SYNCARR_PER_ROW_STORAGE_KEY,
      DEFAULT_LIST_SYNCARR_PER_ROW,
    ),
  )

  function handleDensityChange(next: PosterDensity) {
    setDensity(next)
    writeStoredDensity(LIST_SYNCARR_PER_ROW_STORAGE_KEY, next)
  }

  function handleSync() {
    syncNow.mutate()
  }

  function handleDelete(item: Item) {
    removeItem.mutate({ list_id: item.list_id, trakt_id: item.trakt_id })
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Lists</h2>
        <p className="text-sm text-muted-foreground">
          Trakt lists kept in sync by the engine.
        </p>
      </div>

      <SyncStats />

      <Card>
        <CardHeader className="flex flex-col items-start justify-between gap-4 space-y-0 sm:flex-row">
          <div>
            <CardTitle>Synced lists</CardTitle>
            <CardDescription>
              Manage these from the Settings tab.
            </CardDescription>
          </div>
          <ListsToolbar
            density={density}
            showRemoved={showRemoved}
            syncPending={syncNow.isPending}
            removeAvailablePending={removeAvailable.isPending}
            onDensityChange={handleDensityChange}
            onShowRemovedChange={setShowRemoved}
            onSync={handleSync}
            onRemoveAvailable={() => removeAvailable.mutate()}
          />
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
                    density={density}
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
