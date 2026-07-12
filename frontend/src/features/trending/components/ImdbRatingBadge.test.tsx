import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ImdbRatingBadge } from "@/features/trending/components/ImdbRatingBadge"
import type { TrendingItem } from "@/shared/lib/api"

const ITEM: TrendingItem = {
  source: "trakt",
  media_type: "movie",
  tmdb: 100,
  imdb: "tt1",
  tvdb: null,
  trakt: 1,
  slug: null,
  title: "Dune",
  year: 2021,
  anilist: null,
  poster_url: null,
  seer_status: null,
  imdb_rating: null,
  already_tracked: false,
  in_library: false,
  in_library_available: false,
}

describe("ImdbRatingBadge", () => {
  it("renders nothing while the backfill has not covered the title", () => {
    const { container } = render(<ImdbRatingBadge item={ITEM} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("shows the rating carried on the feed item", () => {
    render(<ImdbRatingBadge item={{ ...ITEM, imdb_rating: 8.62 }} />)
    expect(screen.getByText("8.6")).toBeInTheDocument()
    expect(screen.queryByText(/\(/)).not.toBeInTheDocument()
  })
})
