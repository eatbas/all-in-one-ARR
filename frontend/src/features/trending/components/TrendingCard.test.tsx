import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useTrendingRating: vi.fn(),
  useLists: vi.fn(),
  useAddTrending: vi.fn(),
}))

import {
  useAddTrending,
  useLists,
  useTrendingRating,
} from "@/shared/lib/queries"
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
    anilist: null,
    poster_url: null,
    seer_status: null,
    already_tracked: false,
    in_library: false,
    in_library_available: false,
    ...over,
  }
}

beforeEach(() => {
  // Children hooks: no rating, no owned lists (add disabled), idle mutation.
  vi.mocked(useTrendingRating).mockReturnValue(
    queryResult<TrendingRating>(undefined),
  )
  vi.mocked(useLists).mockReturnValue(queryResult([]))
  vi.mocked(useAddTrending).mockReturnValue(mutationResult(vi.fn(), false))
})

describe("TrendingCard", () => {
  it("renders a poster image when the item has a TMDB id", () => {
    render(
      <ul>
        {[item({})].map((i) => (
          <TrendingCard key="x" item={i} />
        ))}
      </ul>,
    )
    const img = screen.getByRole("img", { name: "Dune" })
    expect(img).toHaveAttribute("src", "/api/posters/movie/100")
  })

  it("passes an IMDb id to the poster endpoint for fallback lookup", () => {
    render(
      <ul>
        <TrendingCard item={item({ imdb: "tt1160419" })} />
      </ul>,
    )
    expect(screen.getByRole("img", { name: "Dune" })).toHaveAttribute(
      "src",
      "/api/posters/movie/100?imdb=tt1160419",
    )
  })

  it("falls back to a placeholder when there is no TMDB id", () => {
    render(
      <ul>
        <TrendingCard item={item({ tmdb: null, title: null })} />
      </ul>,
    )
    expect(
      screen.getByRole("img", { name: "No poster for Untitled" }),
    ).toBeInTheDocument()
  })

  it("renders the direct cover URL when there is no TMDB id but a poster_url", () => {
    // An unmapped AniList title: no TMDB id for the cached-poster pipeline,
    // but the source supplies its own cover art.
    render(
      <ul>
        <TrendingCard
          item={item({
            tmdb: null,
            poster_url: "https://img.anili.st/cover.jpg",
          })}
        />
      </ul>,
    )
    expect(screen.getByRole("img", { name: "Dune" })).toHaveAttribute(
      "src",
      "https://img.anili.st/cover.jpg",
    )
  })

  it("prefers the cached poster over poster_url when a TMDB id exists", () => {
    render(
      <ul>
        <TrendingCard
          item={item({ poster_url: "https://img.anili.st/cover.jpg" })}
        />
      </ul>,
    )
    expect(screen.getByRole("img", { name: "Dune" })).toHaveAttribute(
      "src",
      "/api/posters/movie/100",
    )
  })

  it("falls back to a placeholder when the poster fails to load", () => {
    render(
      <ul>
        <TrendingCard item={item({})} />
      </ul>,
    )
    fireEvent.error(screen.getByRole("img", { name: "Dune" }))
    expect(
      screen.getByRole("img", { name: "No poster for Dune" }),
    ).toBeInTheDocument()
  })

  it("does not show a Tracked badge even when the item is already mirrored", () => {
    render(
      <ul>
        <TrendingCard item={item({ already_tracked: true })} />
      </ul>,
    )
    expect(screen.queryByText("Tracked")).not.toBeInTheDocument()
  })

  it("exposes the source label on the source-link pill for the reveal", () => {
    render(
      <ul>
        <TrendingCard item={item({ source: "tmdb" })} />
      </ul>,
    )
    expect(screen.getByText("TMDB")).toBeInTheDocument()
  })

  it("places the IMDb rating pill in the poster's top-left corner", () => {
    vi.mocked(useTrendingRating).mockReturnValue(
      queryResult<TrendingRating>({ imdb_rating: 7.8, imdb_votes: 44_000 }),
    )
    render(
      <ul>
        <TrendingCard item={item({})} />
      </ul>,
    )
    // The rating sits in the top-left overlay wrapper, not the caption below.
    const rating = screen.getByText("7.8")
    expect(rating.closest(".absolute.left-1.top-1")).not.toBeNull()
    expect(screen.queryByText("(44K)")).not.toBeInTheDocument()
  })

  it("marks a Seer-available title with a green tick indicator", () => {
    render(
      <ul>
        <TrendingCard item={item({ seer_status: 5 })} />
      </ul>,
    )
    expect(screen.getByLabelText("Available")).toHaveClass(
      "ring-emerald-500",
      "ring-inset",
    )
  })

  it("marks a processing title with an amber status indicator", () => {
    render(
      <ul>
        <TrendingCard item={item({ seer_status: 3 })} />
      </ul>,
    )
    const indicator = screen.getByLabelText("Processing")
    expect(indicator).toHaveClass("ring-amber-500")
    expect(indicator).toHaveClass("ring-inset")
  })

  it("shows no status indicator for an unknown Seer status", () => {
    render(
      <ul>
        <TrendingCard item={item({ seer_status: 1 })} />
      </ul>,
    )
    expect(screen.queryByLabelText("Available")).not.toBeInTheDocument()
    expect(screen.queryByLabelText("Requested")).not.toBeInTheDocument()
  })

  it("shows the year and media type", () => {
    render(
      <ul>
        <TrendingCard item={item({ year: null, media_type: "show" })} />
      </ul>,
    )
    expect(screen.getByText("— · show")).toBeInTheDocument()
  })

  it("marks a downloaded library item with a green tick indicator", () => {
    render(
      <ul>
        <TrendingCard
          item={item({ in_library: true, in_library_available: true })}
        />
      </ul>,
    )
    expect(screen.getByLabelText("Available")).toHaveClass(
      "ring-emerald-500",
      "ring-inset",
    )
  })

  it("marks an in-library-but-undownloaded item with an amber status indicator", () => {
    render(
      <ul>
        <TrendingCard
          item={item({ in_library: true, in_library_available: false })}
        />
      </ul>,
    )
    const indicator = screen.getByLabelText("In library, media not downloaded")
    expect(indicator).toHaveClass("ring-amber-500")
    expect(indicator).toHaveClass("ring-inset")
  })

  it.each([
    [5, "h-8", "size-8", "size-4"],
    [6, "h-7", "size-7", "size-3.5"],
    [7, "h-6", "size-6", "size-3"],
    [8, "h-[22px]", "size-[22px]", "size-3"],
    [9, "h-5", "size-5", "size-[11px]"],
    [10, "h-[18px]", "size-[18px]", "size-2.5"],
    [11, "h-4", "size-4", "size-2"],
  ] as const)(
    "uses matching collapsed pill geometry at density %i",
    (density, shellHeight, slotSize, iconSize) => {
      render(
        <ul>
          <TrendingCard item={item({ seer_status: 3 })} density={density} />
        </ul>,
      )

      const source = screen.getByRole("link", { name: /open .* on tmdb/i })
      const add = screen.getByRole("button", { name: /add/i })
      const status = screen.getByLabelText("Processing")

      for (const control of [source, add, status]) {
        // The shell fixes only the height and hugs its content; the icon slot
        // keeps the square size that renders the resting circle.
        expect(control).toHaveClass(shellHeight, "w-fit")
        expect(control).toHaveClass("rounded-full")
        expect(control.querySelector("[data-pill-icon-slot]")).toHaveClass(
          slotSize,
        )
        expect(control.querySelector("svg")).toHaveClass(iconSize)
      }

      expect(source).not.toHaveClass("px-2")
      expect(source).not.toHaveClass("px-1.5")
      // The add control is a Button; its `sm` variant's own height and padding
      // (h-8, px-3) must be merged away by the pill shell so it stays a circle
      // matching the link and status pills. Its height already tracks the shell
      // height asserted above; here we confirm the variant padding is gone.
      expect(add).toHaveClass("px-0")
      expect(add).not.toHaveClass("px-3")
    },
  )

  it("keeps reveal labels truncated and bounded", () => {
    render(
      <ul>
        <TrendingCard
          item={item({ source: "trakt", slug: "dune", seer_status: 3 })}
        />
      </ul>,
    )

    for (const label of ["Trakt", "Pending", "Add"]) {
      expect(screen.getByText(label)).toHaveClass("overflow-hidden")
      expect(screen.getByText(label)).toHaveClass("text-ellipsis")
      expect(screen.getByText(label)).toHaveClass("whitespace-nowrap")
    }
  })

  it("pads each revealed label on its outer edge so the word stays centred", () => {
    render(
      <ul>
        <TrendingCard
          item={item({ source: "trakt", slug: "dune", seer_status: 3 })}
        />
      </ul>,
    )

    // Labels sit left of the icon on the link and add pills, right of it on
    // the status pill; the expanded padding always lands on the outer edge.
    expect(screen.getByText("Trakt")).toHaveClass("group-hover/link:pl-2")
    expect(screen.getByText("Add")).toHaveClass("group-hover/add:pl-2")
    expect(screen.getByText("Pending")).toHaveClass("group-hover/status:pr-2")
  })

  it("omits the status indicator when the item is not in the library", () => {
    render(
      <ul>
        <TrendingCard item={item({})} />
      </ul>,
    )
    expect(screen.queryByLabelText("Available")).not.toBeInTheDocument()
  })

  it("renders a hover overlay with the full title and year", () => {
    render(
      <ul>
        <TrendingCard item={item({})} />
      </ul>,
    )
    // The title appears twice: the static line below the poster and the overlay.
    expect(screen.getAllByText("Dune")).toHaveLength(2)
    // The overlay is aria-hidden — it duplicates content assistive technology
    // already receives from the static lines and the poster alt text.
    const year = screen.getByText("2021")
    expect(year.closest("[aria-hidden='true']")).not.toBeNull()
  })

  it("links a TMDB-sourced item to its themoviedb.org page", () => {
    render(
      <ul>
        <TrendingCard item={item({ source: "tmdb", tmdb: 603 })} />
      </ul>,
    )
    expect(
      screen.getByRole("link", { name: /open .* on tmdb/i }),
    ).toHaveAttribute("href", "https://www.themoviedb.org/movie/603")
  })

  it("links a Trakt-sourced item to its trakt.tv slug page", () => {
    render(
      <ul>
        <TrendingCard
          item={item({
            source: "trakt",
            media_type: "show",
            slug: "severance",
          })}
        />
      </ul>,
    )
    expect(
      screen.getByRole("link", { name: /open .* on trakt/i }),
    ).toHaveAttribute("href", "https://trakt.tv/shows/severance")
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
    expect(
      screen.getByRole("link", { name: /open .* on seer/i }),
    ).toHaveAttribute("href", "https://seer.example.com/movie/42")
  })

  it("omits the source link when no URL can be resolved", () => {
    // A Trakt item without a slug has no resolvable trakt.tv URL.
    render(
      <ul>
        <TrendingCard item={item({ source: "trakt", slug: null })} />
      </ul>,
    )
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
  })
})
