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
  seer_status: null,
  already_tracked: false,
  in_library: false,
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

  it("shows the rating with millions-formatted votes", () => {
    setRating({ imdb_rating: 8.62, imdb_votes: 1_234_567 })
    render(<ImdbRatingBadge item={ITEM} />)
    expect(screen.getByText("8.6")).toBeInTheDocument()
    expect(screen.getByText("(1.2M)")).toBeInTheDocument()
  })

  it("formats thousands-scale votes", () => {
    setRating({ imdb_rating: 7, imdb_votes: 4200 })
    render(<ImdbRatingBadge item={ITEM} />)
    expect(screen.getByText("(4.2k)")).toBeInTheDocument()
  })

  it("formats small vote counts", () => {
    setRating({ imdb_rating: 6, imdb_votes: 999 })
    render(<ImdbRatingBadge item={ITEM} />)
    expect(screen.getByText("(999)")).toBeInTheDocument()
  })

  it("omits the vote count when it is null", () => {
    setRating({ imdb_rating: 6, imdb_votes: null })
    render(<ImdbRatingBadge item={ITEM} />)
    expect(screen.getByText("6.0")).toBeInTheDocument()
    expect(screen.queryByText(/\(/)).not.toBeInTheDocument()
  })
})
