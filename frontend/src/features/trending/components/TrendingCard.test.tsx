import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useTrendingRating: vi.fn(),
  useLists: vi.fn(),
  useAddTrending: vi.fn(),
}))

import { useAddTrending, useLists, useTrendingRating } from "@/shared/lib/queries"
import { TrendingCard } from "@/features/trending/components/TrendingCard"
import { mutationResult, queryResult } from "@/shared/test/mock-query"
import type { TrendingItem, TrendingRating } from "@/shared/lib/api"

function item(over: Partial<TrendingItem>): TrendingItem {
  return {
    source: "tmdb",
    media_type: "movie",
    tmdb: 100,
    imdb: null,
    tvdb: null,
    trakt: null,
    slug: null,
    title: "Dune",
    year: 2021,
    seer_status: null,
    already_tracked: false,
    in_library: false,
    in_library_available: false,
    ...over,
  }
}

beforeEach(() => {
  // Children hooks: no rating, no owned lists (add disabled), idle mutation.
  vi.mocked(useTrendingRating).mockReturnValue(queryResult<TrendingRating>(undefined))
  vi.mocked(useLists).mockReturnValue(queryResult([]))
  vi.mocked(useAddTrending).mockReturnValue(mutationResult(vi.fn(), false))
})

describe("TrendingCard", () => {
  it("renders a poster image when the item has a TMDB id", () => {
    render(<ul>{[item({})].map((i) => <TrendingCard key="x" item={i} />)}</ul>)
    const img = screen.getByRole("img", { name: "Dune" })
    expect(img).toHaveAttribute("src", "/api/posters/movie/100")
  })

  it("passes an IMDb id to the poster endpoint for fallback lookup", () => {
    render(<ul><TrendingCard item={item({ imdb: "tt1160419" })} /></ul>)
    expect(screen.getByRole("img", { name: "Dune" })).toHaveAttribute(
      "src",
      "/api/posters/movie/100?imdb=tt1160419",
    )
  })

  it("falls back to a placeholder when there is no TMDB id", () => {
    render(<ul><TrendingCard item={item({ tmdb: null, title: null })} /></ul>)
    expect(screen.getByRole("img", { name: "No poster for Untitled" })).toBeInTheDocument()
  })

  it("falls back to a placeholder when the poster fails to load", () => {
    render(<ul><TrendingCard item={item({})} /></ul>)
    fireEvent.error(screen.getByRole("img", { name: "Dune" }))
    expect(screen.getByRole("img", { name: "No poster for Dune" })).toBeInTheDocument()
  })

  it("shows a Tracked badge when the item is already mirrored", () => {
    render(<ul><TrendingCard item={item({ already_tracked: true })} /></ul>)
    expect(screen.getByText("Tracked")).toBeInTheDocument()
  })

  it("shows a green Seer status badge when the title is Available", () => {
    render(<ul><TrendingCard item={item({ seer_status: 5 })} /></ul>)
    expect(screen.getByText("Available")).toHaveClass("bg-emerald-500")
  })

  it("shows an amber Seer status badge while Processing", () => {
    render(<ul><TrendingCard item={item({ seer_status: 3 })} /></ul>)
    expect(screen.getByText("Processing")).toHaveClass("bg-amber-500")
  })

  it("shows no status badge for an unknown Seer status", () => {
    render(<ul><TrendingCard item={item({ seer_status: 1 })} /></ul>)
    expect(screen.queryByText("Available")).not.toBeInTheDocument()
    expect(screen.queryByText("Requested")).not.toBeInTheDocument()
  })

  it("shows the year and media type", () => {
    render(<ul><TrendingCard item={item({ year: null, media_type: "show" })} /></ul>)
    expect(screen.getByText("— · show")).toBeInTheDocument()
  })

  it("marks a downloaded library item with a green In-library badge", () => {
    render(
      <ul>
        <TrendingCard item={item({ in_library: true, in_library_available: true })} />
      </ul>,
    )
    expect(screen.getByLabelText("In library")).toHaveClass("bg-emerald-500")
  })

  it("marks an in-library-but-undownloaded item with an amber badge", () => {
    render(
      <ul>
        <TrendingCard item={item({ in_library: true, in_library_available: false })} />
      </ul>,
    )
    const badge = screen.getByLabelText("In library, media not downloaded")
    expect(badge).toHaveTextContent("In library")
    expect(badge).toHaveClass("bg-amber-500")
  })

  it("omits the In-library badge when the item is not in the library", () => {
    render(<ul><TrendingCard item={item({})} /></ul>)
    expect(screen.queryByText("In library")).not.toBeInTheDocument()
  })

  it("links a TMDB-sourced item to its themoviedb.org page", () => {
    render(<ul><TrendingCard item={item({ source: "tmdb", tmdb: 603 })} /></ul>)
    expect(screen.getByRole("link", { name: /open .* on tmdb/i })).toHaveAttribute(
      "href",
      "https://www.themoviedb.org/movie/603",
    )
  })

  it("links a Trakt-sourced item to its trakt.tv slug page", () => {
    render(
      <ul>
        <TrendingCard
          item={item({ source: "trakt", media_type: "show", slug: "severance" })}
        />
      </ul>,
    )
    expect(screen.getByRole("link", { name: /open .* on trakt/i })).toHaveAttribute(
      "href",
      "https://trakt.tv/shows/severance",
    )
  })

  it("links a Seer-sourced item to the configured Seer instance", () => {
    render(
      <ul>
        <TrendingCard
          item={item({ source: "seer", tmdb: 42 })}
          seerUrl="https://seer.example.com"
        />
      </ul>,
    )
    expect(screen.getByRole("link", { name: /open .* on seer/i })).toHaveAttribute(
      "href",
      "https://seer.example.com/movie/42",
    )
  })

  it("omits the source link when no URL can be resolved", () => {
    // A Trakt item without a slug has no resolvable trakt.tv URL.
    render(<ul><TrendingCard item={item({ source: "trakt", slug: null })} /></ul>)
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
  })
})
