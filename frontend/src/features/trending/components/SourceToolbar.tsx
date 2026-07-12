import { PosterDensityControl } from "@/shared/components/poster-grid/poster-grid-density-control"
import { Switch } from "@/shared/components/ui/switch"
import { formatRelativeTime } from "@/shared/lib/format"
import type { ItemType, TrendingCategory } from "@/shared/lib/api"
import type { PerRow } from "@/features/trending/trending-tab"
import { Toggle } from "@/features/trending/components/Toggle"

interface SourceToolbarProps {
  media: ItemType
  category: TrendingCategory
  hideAvailable: boolean
  perRow: PerRow
  isFetching: boolean
  isInitialLoading: boolean
  lastSyncedAt?: string | null
  onChangeMedia: (media: ItemType) => void
  onChangeCategory: (category: TrendingCategory) => void
  onChangeHideAvailable: (hide: boolean) => void
  onChangePerRow: (perRow: PerRow) => void
}

/**
 * Controls for a single source panel: media/category toggles, refresh metadata,
 * density selector, and the hide-available switch.
 */
export function SourceToolbar({
  media,
  category,
  hideAvailable,
  perRow,
  isFetching,
  isInitialLoading,
  lastSyncedAt,
  onChangeMedia,
  onChangeCategory,
  onChangeHideAvailable,
  onChangePerRow,
}: SourceToolbarProps) {
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
      <Toggle
        ariaLabel="Category"
        value={category}
        onChange={onChangeCategory}
        options={[
          { value: "trending", label: "Trending" },
          { value: "popular", label: "Popular" },
        ]}
      />
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
