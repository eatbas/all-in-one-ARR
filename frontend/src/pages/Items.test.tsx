import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/lib/queries", () => ({ useItems: vi.fn() }))

import { useItems } from "@/lib/queries"
import { Items } from "@/pages/Items"
import type { Item } from "@/lib/api"
import { queryResult } from "@/test/mock-query"

const base = {
  tmdb: null,
  tvdb: null,
  imdb: null,
  jellyseerr_request_id: null,
  created_at: "2024-01-01T00:00:00Z",
} as const

const items: Item[] = [
  {
    ...base,
    trakt_id: 1,
    list_id: "L",
    title: "Alpha",
    year: 2020,
    type: "movie",
    status: "synced",
    updated_at: "2024-01-01T10:00:00Z",
  },
  {
    ...base,
    trakt_id: 2,
    list_id: "L",
    title: "Beta",
    year: null,
    type: "show",
    status: "requested",
    updated_at: "bad-date",
  },
  {
    ...base,
    trakt_id: 3,
    list_id: "L",
    title: "Gamma",
    year: 2019,
    type: "movie",
    status: "available",
    updated_at: "2024-02-01T10:00:00Z",
  },
  {
    ...base,
    trakt_id: 4,
    list_id: "L",
    title: "Delta",
    year: 2018,
    type: "show",
    status: "removed",
    updated_at: "2024-03-01T10:00:00Z",
  },
]

describe("Items", () => {
  it("shows a loading row while items are pending", () => {
    vi.mocked(useItems).mockReturnValue(queryResult<Item[]>(undefined, true))
    render(<Items />)
    expect(screen.getByText("Loading items…")).toBeInTheDocument()
  })

  it("shows an empty row when no items match", () => {
    vi.mocked(useItems).mockReturnValue(queryResult<Item[]>([], false))
    render(<Items />)
    expect(screen.getByText("No items match this filter.")).toBeInTheDocument()
  })

  it("treats undefined data as empty once the query has settled", () => {
    vi.mocked(useItems).mockReturnValue(queryResult<Item[]>(undefined, false))
    render(<Items />)
    expect(screen.getByText("No items match this filter.")).toBeInTheDocument()
  })

  it("renders rows, handling a null year and an invalid timestamp", () => {
    vi.mocked(useItems).mockReturnValue(queryResult<Item[]>(items, false))
    render(<Items />)

    expect(screen.getByText("Alpha")).toBeInTheDocument()
    expect(screen.getByText("—")).toBeInTheDocument() // Beta has a null year
    expect(screen.getByText("bad-date")).toBeInTheDocument() // invalid timestamp
    // Each row shows its source list in the new List column.
    expect(screen.getAllByText("L")).toHaveLength(items.length)
    // Every status renders its styled badge.
    expect(screen.getByText("synced")).toBeInTheDocument()
    expect(screen.getByText("available")).toBeInTheDocument()
    expect(screen.getByText("removed")).toBeInTheDocument()
  })

  it("re-queries with the chosen status filter", async () => {
    const user = userEvent.setup()
    vi.mocked(useItems).mockReturnValue(queryResult<Item[]>(items, false))
    render(<Items />)

    // "all" maps to an undefined filter on first render.
    expect(useItems).toHaveBeenCalledWith(undefined)

    await user.click(screen.getByRole("button", { name: /all statuses/i }))
    await user.click(
      await screen.findByRole("menuitemradio", { name: "Requested" }),
    )

    expect(useItems).toHaveBeenLastCalledWith("requested")
  })
})
