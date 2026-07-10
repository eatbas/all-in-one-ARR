import { StarIcon } from "lucide-react"

import { useTrendingRating } from "@/shared/lib/queries"
import type { TrendingItem } from "@/shared/lib/api"
import { cn } from "@/shared/lib/utils"
import { formatCompactVotes } from "@/shared/lib/format"
import type { PillDensity } from "@/features/trending/components/poster-pill-variants"

/** Star and text sizes per posters-per-row density; both shrink as the grid densifies. */
const RATING_SIZE: Record<
  PillDensity,
  { star: string; rating: string; votes: string }
> = {
  5: { star: "size-3", rating: "text-[11px]", votes: "text-[10px]" },
  6: { star: "size-3", rating: "text-[11px]", votes: "text-[10px]" },
  7: { star: "size-2.5", rating: "text-[10px]", votes: "text-[9px]" },
  8: { star: "size-2.5", rating: "text-[10px]", votes: "text-[9px]" },
  9: { star: "size-2.5", rating: "text-[9px]", votes: "text-[8px]" },
  10: { star: "size-2", rating: "text-[9px]", votes: "text-[8px]" },
  11: { star: "size-2", rating: "text-[8px]", votes: "text-[8px]" },
}

/**
 * IMDb rating pill for a trending card's top-left corner. Fetches the rating
 * lazily via OMDb and renders nothing until it resolves (or when no rating is
 * available), so a card never shows a broken or empty rating. The star and
 * rating sit on top, the compact vote count in parentheses beneath; both scale
 * down with the posters-per-row density.
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
  const { data } = useTrendingRating(item, true)
  if (!data || data.imdb_rating === null) {
    return null
  }
  const size = RATING_SIZE[density]
  return (
    <div
      title="IMDb rating"
      className="inline-flex flex-col items-start rounded-md bg-background/85 px-1 py-0.5 leading-tight backdrop-blur-sm"
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
        <span>{data.imdb_rating.toFixed(1)}</span>
      </span>
      {data.imdb_votes !== null ? (
        <span className={cn(size.votes, "text-muted-foreground")}>
          ({formatCompactVotes(data.imdb_votes)})
        </span>
      ) : null}
    </div>
  )
}
