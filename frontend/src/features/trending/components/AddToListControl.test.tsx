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
  anilist: null,
  poster_url: null,
  seer_status: null,
  imdb_rating: null,
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

  it("disables the control when the item carries no usable id", () => {
    // An unmapped AniList title: owned lists exist, but Trakt could not
    // resolve an add without a Trakt/TMDB/TVDB/IMDb id.
    vi.mocked(useLists).mockReturnValue(
      queryResult([listSummary({ slug: "movies", name: "Movies" })]),
    )
    render(
      <AddToListControl
        item={{ ...ITEM, tmdb: null, imdb: null, tvdb: null, trakt: null }}
      />,
    )
    const button = screen.getByRole("button", { name: /add/i })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute("title", expect.stringMatching(/no known/i))
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

  it("opens the add menu without locking body scroll, so the sticky header and sidebar stay anchored", async () => {
    vi.mocked(useLists).mockReturnValue(
      queryResult([listSummary({ slug: "movies", name: "Movies" })]),
    )
    const user = userEvent.setup()
    render(<AddToListControl item={ITEM} />)
    await user.click(screen.getByRole("button", { name: /add/i }))
    // The menu is open…
    expect(
      await screen.findByRole("menuitem", { name: "Movies" }),
    ).toBeInTheDocument()
    // …but the non-modal menu must not engage react-remove-scroll's body
    // scroll-lock (`data-scroll-locked` → `overflow: hidden` on <body>), which is
    // what detaches the sticky Topbar/Sidebar when the page is scrolled down.
    expect(document.body).not.toHaveAttribute("data-scroll-locked")
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
    [5, "h-8", "size-8", "size-4", "group-hover/add:pl-2"],
    [6, "h-7", "size-7", "size-3.5", "group-hover/add:pl-1.5"],
    [7, "h-7", "size-7", "size-3.5", "group-hover/add:pl-1.5"],
  ] as const)(
    "uses the shared pill shell at density %i",
    (density, shellHeight, slotSize, iconSize, labelOuterPadding) => {
      vi.mocked(useLists).mockReturnValue(
        queryResult([listSummary({ slug: "movies", name: "Movies" })]),
      )
      render(<AddToListControl item={ITEM} density={density} />)

      const button = screen.getByRole("button", { name: /add/i })
      // The shell fixes only the height and hugs its content (w-fit); the icon
      // slot keeps the square size that renders the resting circle.
      expect(button).toHaveClass(shellHeight, "w-fit")
      expect(button).toHaveClass("rounded-full")
      // The Button `sm` variant's own height and padding (h-8, px-3) must be
      // merged away so the add pill matches the link and status circles; its
      // height already tracks the shell height asserted above.
      expect(button).toHaveClass("px-0")
      expect(button).not.toHaveClass("px-3")
      expect(button.querySelector("[data-pill-icon-slot]")).toHaveClass(
        slotSize,
      )
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
