import { StarIcon } from "lucide-react"

import { useTrendingRating } from "@/shared/lib/queries"
import type { TrendingItem } from "@/shared/lib/api"

/** Format a vote count compactly: "1.2M", "4.2k", or the raw number. */
function formatVotes(votes: number): string {
  if (votes >= 1_000_000) {
    return `${(votes / 1_000_000).toFixed(1)}M`
  }
  if (votes >= 1_000) {
    return `${(votes / 1_000).toFixed(1)}k`
  }
  return String(votes)
}

/**
 * IMDb rating overlay for a trending card. Fetches the rating lazily via OMDb and
 * renders nothing until it resolves or when no rating is available, so a card
 * never shows a broken or empty rating.
 */
export function ImdbRatingBadge({ item }: { item: TrendingItem }) {
  const { data } = useTrendingRating(item, true)
  if (!data || data.imdb_rating === null) {
    return null
  }
  return (
    <span
      className="inline-flex items-center gap-1 text-xs text-muted-foreground"
      title="IMDb rating"
    >
      <StarIcon className="size-3 fill-amber-400 text-amber-400" />
      <span className="font-medium text-foreground">
        {data.imdb_rating.toFixed(1)}
      </span>
      {data.imdb_votes !== null ? (
        <span>({formatVotes(data.imdb_votes)})</span>
      ) : null}
    </span>
  )
}
