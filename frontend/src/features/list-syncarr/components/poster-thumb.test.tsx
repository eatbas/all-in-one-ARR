import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { PosterThumb } from "@/features/list-syncarr/components/poster-thumb"
import type { Item } from "@/shared/lib/api"

const base: Item = {
  trakt_id: 1,
  type: "movie",
  title: "Dune",
  year: 2021,
  tmdb: 438631,
  tvdb: null,
  imdb: "tt1",
  list_id: "movies",
  seer_request_id: null,
  status: "available",
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
}

describe("PosterThumb", () => {
  it("renders the poster image for an item with a TMDB id", () => {
    render(<PosterThumb item={base} />)
    expect(screen.getByRole("img", { name: "Dune" })).toHaveAttribute(
      "src",
      "/api/posters/movie/438631",
    )
  })

  it("shows a placeholder when the item has no TMDB id", () => {
    render(<PosterThumb item={{ ...base, tmdb: null, title: "NoPoster" }} />)
    expect(
      screen.getByRole("img", { name: "No poster for NoPoster" }),
    ).toBeInTheDocument()
  })

  it("falls back to the placeholder when the poster fails to load", () => {
    render(<PosterThumb item={base} />)
    fireEvent.error(screen.getByRole("img", { name: "Dune" }))
    expect(
      screen.getByRole("img", { name: "No poster for Dune" }),
    ).toBeInTheDocument()
  })

  it("exposes the title as a hover tooltip on the poster", () => {
    render(<PosterThumb item={base} />)
    expect(screen.getByRole("img", { name: "Dune" })).toHaveAttribute(
      "title",
      "Dune",
    )
  })

  it("exposes the title as a hover tooltip on the placeholder", () => {
    render(<PosterThumb item={{ ...base, tmdb: null, title: "NoPoster" }} />)
    expect(
      screen.getByRole("img", { name: "No poster for NoPoster" }),
    ).toHaveAttribute("title", "NoPoster")
  })
})
