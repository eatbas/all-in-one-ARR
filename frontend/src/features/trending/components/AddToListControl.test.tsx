import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useLists: vi.fn(),
  useAddTrending: vi.fn(),
}))

import { useAddTrending, useLists } from "@/shared/lib/queries"
import { AddToListControl } from "@/features/trending/components/AddToListControl"
import { queryResult } from "@/shared/test/mock-query"
import type { ListSummary, TrendingItem } from "@/shared/lib/api"

/** Mutation-shaped stub; typed loosely as these are test doubles. */
function mutation(mutate: unknown, isPending = false) {
  return { mutate, isPending } as never
}

const ITEM: TrendingItem = {
  source: "tmdb",
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
  in_library_available: false,
}

function listSummary(over: Partial<ListSummary>): ListSummary {
  return {
    owner_user: "me",
    slug: "movies",
    name: "Movies",
    item_count: 1,
    removed_count: 0,
    last_synced_at: null,
    next_sync_at: null,
    interval_minutes: 15,
    ...over,
  }
}

let mutate: ReturnType<typeof vi.fn>

beforeEach(() => {
  mutate = vi.fn()
  vi.mocked(useAddTrending).mockReturnValue(mutation(mutate, false))
})

describe("AddToListControl", () => {
  it("disables the control when there is no owned list", () => {
    // Only a watchlist and a non-owned (official) list, both filtered out.
    vi.mocked(useLists).mockReturnValue(
      queryResult([
        listSummary({ slug: "watchlist", name: "watchlist" }),
        listSummary({ owner_user: "official", slug: "9", name: "Official" }),
      ]),
    )
    render(<AddToListControl item={ITEM} />)
    expect(screen.getByRole("button", { name: /add/i })).toBeDisabled()
  })

  it("treats missing list data as no owned lists", () => {
    vi.mocked(useLists).mockReturnValue(queryResult<ListSummary[]>(undefined))
    render(<AddToListControl item={ITEM} />)
    expect(screen.getByRole("button", { name: /add/i })).toBeDisabled()
  })

  it("adds the item to a chosen owned list", async () => {
    vi.mocked(useLists).mockReturnValue(
      queryResult([listSummary({ slug: "movies", name: "Movies" })]),
    )
    const user = userEvent.setup()
    render(<AddToListControl item={ITEM} />)
    await user.click(screen.getByRole("button", { name: /add/i }))
    await user.click(screen.getByRole("menuitem", { name: "Movies" }))
    expect(mutate).toHaveBeenCalledWith({
      media_type: "movie",
      owner_user: "me",
      slug: "movies",
      tmdb: 100,
      imdb: "tt1",
      trakt: 1,
      tvdb: null,
      title: "Dune",
    })
  })

  it("keeps the hover-revealed Add label present in the DOM", () => {
    vi.mocked(useLists).mockReturnValue(
      queryResult([listSummary({ slug: "movies", name: "Movies" })]),
    )
    render(<AddToListControl item={ITEM} />)
    // The label is collapsed via CSS and revealed on hover/focus; it must stay
    // in the DOM so the expansion has content to animate.
    expect(screen.getByText("Add")).toBeInTheDocument()
  })

  it.each([
    [5, "size-8", "size-4", "group-hover/add:pl-2"],
    [6, "size-7", "size-3.5", "group-hover/add:pl-1.5"],
    [7, "size-6", "size-3", "group-hover/add:pl-1.5"],
  ] as const)(
    "uses the shared pill shell at density %i",
    (density, shellSize, iconSize, labelOuterPadding) => {
      vi.mocked(useLists).mockReturnValue(
        queryResult([listSummary({ slug: "movies", name: "Movies" })]),
      )
      render(<AddToListControl item={ITEM} density={density} />)

      const button = screen.getByRole("button", { name: /add/i })
      expect(button).toHaveClass(shellSize)
      // The Button variant's fixed h-8 must be merged away so the add pill
      // matches the link and status circles at every density.
      expect(button).not.toHaveClass("h-8")
      expect(button).toHaveClass("rounded-full")
      expect(button).toHaveClass("px-0")
      expect(button.querySelector("[data-pill-icon-slot]")).toHaveClass(shellSize)
      expect(button.querySelector("svg")).toHaveClass(iconSize)
      expect(screen.getByText("Add")).toHaveClass(labelOuterPadding)
    },
  )

  it("disables the trigger while an add is pending", () => {
    vi.mocked(useLists).mockReturnValue(
      queryResult([listSummary({ slug: "movies", name: "Movies" })]),
    )
    vi.mocked(useAddTrending).mockReturnValue(mutation(mutate, true))
    render(<AddToListControl item={ITEM} />)
    expect(screen.getByRole("button", { name: /add/i })).toBeDisabled()
  })
})
