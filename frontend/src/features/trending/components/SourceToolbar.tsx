import { PosterDensityControl } from "@/shared/components/poster-grid/poster-grid-density-control"
import { Input } from "@/shared/components/ui/input"
import { Switch } from "@/shared/components/ui/switch"
import { formatRelativeTime } from "@/shared/lib/format"
import type { ItemType, TrendingCategory } from "@/shared/lib/api"
import type { PerRow } from "@/features/trending/trending-tab"
import { Toggle } from "@/features/trending/components/Toggle"

interface SourceToolbarProps {
  media: ItemType
  category: TrendingCategory
  search: string
  hideAvailable: boolean
  perRow: PerRow
  isFetching: boolean
  isInitialLoading: boolean
  lastSyncedAt?: string | null
  onChangeMedia: (media: ItemType) => void
  onChangeCategory: (category: TrendingCategory) => void
  onChangeSearch: (search: string) => void
  onChangeHideAvailable: (hide: boolean) => void
  onChangePerRow: (perRow: PerRow) => void
}

/**
 * Controls for a single source panel: media/category toggles, the title search
 * box, refresh metadata, density selector, and the hide-available switch.
 */
export function SourceToolbar({
  media,
  category,
  search,
  hideAvailable,
  perRow,
  isFetching,
  isInitialLoading,
  lastSyncedAt,
  onChangeMedia,
  onChangeCategory,
  onChangeSearch,
  onChangeHideAvailable,
  onChangePerRow,
}: SourceToolbarProps) {
  const searchActive = search.trim().length > 0
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Toggle
        ariaLabel="Media type"
        value={media}
        onChange={onChangeMedia}
        options={[
          { value: "movie", label: "Movies" },
          { value: "show", label: "Shows" },
        ]}
      />
      {/* Search bypasses the trending/popular split, so the category toggle is
          greyed out (not hidden — the layout stays put) while a query is set. */}
      <Toggle
        ariaLabel="Category"
        value={category}
        onChange={onChangeCategory}
        disabled={searchActive}
        options={[
          { value: "trending", label: "Trending" },
          { value: "popular", label: "Popular" },
        ]}
      />
      <div className="w-52">
        <Input
          type="search"
          aria-label="Search titles"
          placeholder="Search titles…"
          value={search}
          onChange={(event) => onChangeSearch(event.target.value)}
        />
      </div>
      <div className="ml-auto flex items-center gap-3">
        {isFetching && !isInitialLoading ? (
          <span className="text-xs text-muted-foreground">Refreshing</span>
        ) : null}
        {lastSyncedAt ? (
          <span className="text-xs text-muted-foreground">
            Updated {formatRelativeTime(lastSyncedAt)}
          </span>
        ) : null}
        <PosterDensityControl value={perRow} onChange={onChangePerRow} />
        <div className="flex items-center gap-2">
          <Switch
            aria-label="Hide available items"
            checked={hideAvailable}
            onCheckedChange={onChangeHideAvailable}
          />
          <span className="text-sm text-muted-foreground">Hide available</span>
        </div>
      </div>
    </div>
  )
}
