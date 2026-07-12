import { StarIcon } from "lucide-react"

import type { TrendingItem } from "@/shared/lib/api"
import { cn } from "@/shared/lib/utils"
import type { PillDensity } from "@/shared/components/poster-pill/poster-pill-variants"

/** Star and rating sizes per posters-per-row density. */
const RATING_SIZE: Record<PillDensity, { star: string; rating: string }> = {
  5: { star: "size-3", rating: "text-[11px]" },
  6: { star: "size-3", rating: "text-[11px]" },
  7: { star: "size-2.5", rating: "text-[10px]" },
  8: { star: "size-2.5", rating: "text-[10px]" },
  9: { star: "size-2.5", rating: "text-[9px]" },
  10: { star: "size-2", rating: "text-[9px]" },
  11: { star: "size-2", rating: "text-[8px]" },
}

/**
 * IMDb rating pill for a trending card's top-left corner. Renders the rating
 * the feed payload carries (`item.imdb_rating`, filled by the backend's
 * budgeted backfill) and nothing while it is still null, so a card never shows
 * a broken or empty rating. The star and rating scale down with the
 * posters-per-row density.
 */
export function ImdbRatingBadge({
  item,
  density = 5,
}: {
  item: TrendingItem
  /** Posters-per-row density; controls the star and text size. Defaults to the
   *  largest size for consumers that do not know the grid density. */
  density?: PillDensity
}) {
  if (item.imdb_rating === null) {
    return null
  }
  const size = RATING_SIZE[density]
  return (
    <div
      title="IMDb rating"
      className="inline-flex items-center rounded-md bg-background/85 px-1 py-0.5 leading-tight backdrop-blur-sm"
    >
      <span
        className={cn(
          "inline-flex items-center gap-0.5 font-semibold text-foreground",
          size.rating,
        )}
      >
        <StarIcon
          aria-hidden="true"
          className={cn(size.star, "fill-amber-400 text-amber-400")}
        />
        <span>{item.imdb_rating.toFixed(1)}</span>
      </span>
    </div>
  )
}
