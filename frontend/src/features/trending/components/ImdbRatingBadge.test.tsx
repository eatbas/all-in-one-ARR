import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({ useTrendingRating: vi.fn() }))

import { useTrendingRating } from "@/shared/lib/queries"
import { ImdbRatingBadge } from "@/features/trending/components/ImdbRatingBadge"
import { queryResult } from "@/shared/test/mock-query"
import type { TrendingItem, TrendingRating } from "@/shared/lib/api"

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
  already_tracked: false,
  in_library: false,
  in_library_available: false,
}

function setRating(data: TrendingRating | undefined) {
  vi.mocked(useTrendingRating).mockReturnValue(queryResult(data))
}

describe("ImdbRatingBadge", () => {
  it("renders nothing while the rating is loading", () => {
    setRating(undefined)
    const { container } = render(<ImdbRatingBadge item={ITEM} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("renders nothing when no rating is available", () => {
    setRating({ imdb_rating: null, imdb_votes: null })
    const { container } = render(<ImdbRatingBadge item={ITEM} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("shows the rating without the vote count", () => {
    setRating({ imdb_rating: 8.62, imdb_votes: 1_234_567 })
    render(<ImdbRatingBadge item={ITEM} />)
    expect(screen.getByText("8.6")).toBeInTheDocument()
    expect(screen.queryByText(/\(/)).not.toBeInTheDocument()
  })
})
