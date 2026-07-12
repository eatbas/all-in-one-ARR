import { GRID_COLS } from "@/shared/components/poster-grid/poster-grid-density"
import type { PerRow } from "@/features/trending/trending-tab"
import { TrendingCard } from "@/features/trending/components/TrendingCard"
import type { TrendingItem } from "@/shared/lib/api"

interface TrendingResultGridProps {
  perRow: PerRow
  items: TrendingItem[]
  seerUrl?: string
  sentinelRef: React.Ref<HTMLDivElement>
  hasMore: boolean
}

/** Rendered grid of trending cards with an infinite-scroll sentinel when needed. */
export function TrendingResultGrid({
  perRow,
  items,
  seerUrl,
  sentinelRef,
  hasMore,
}: TrendingResultGridProps) {
  return (
    <>
      <ul className={GRID_COLS[perRow]}>
        {items.map((item, index) => (
          <TrendingCard
            // The index keeps the key unique even if two items share a tmdb/title.
            key={`${item.source}:${item.media_type}:${item.tmdb ?? item.title}:${index}`}
            item={item}
            seerUrl={seerUrl}
            density={perRow}
          />
        ))}
      </ul>
      {hasMore ? (
        <div
          ref={sentinelRef}
          aria-hidden="true"
          className="h-8"
          data-testid="trending-scroll-sentinel"
        />
      ) : null}
    </>
  )
}
