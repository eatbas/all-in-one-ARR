import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useTrending: vi.fn(),
  useTrendingRating: vi.fn(),
  useTrendingStatus: vi.fn(),
  useLists: vi.fn(),
  useAddTrending: vi.fn(),
  useServiceSettings: vi.fn(),
}))

import {
  useAddTrending,
  useLists,
  useServiceSettings,
  useTrending,
  useTrendingRating,
  useTrendingStatus,
} from "@/shared/lib/queries"
import { Trending } from "@/features/trending/Trending"
import {
  TRENDING_PER_ROW_STORAGE_KEY,
  TRENDING_TAB_STORAGE_KEY,
} from "@/features/trending/trending-tab"
import { mutationResult, queryResult } from "@/shared/test/mock-query"
import type { ServicesSettings, TrendingItem, TrendingRating } from "@/shared/lib/api"

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
  in_library_available: false,
}

/** A list of `n` distinct trending items titled "Item 1".."Item n". */
function items(n: number): TrendingItem[] {
  return Array.from({ length: n }, (_, index) => ({
    ...ITEM,
    tmdb: index + 1,
    title: `Item ${index + 1}`,
  }))
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(useTrending).mockReturnValue(queryResult([ITEM]))
  vi.mocked(useTrendingRating).mockReturnValue(queryResult<TrendingRating>(undefined))
  vi.mocked(useTrendingStatus).mockReturnValue(
    queryResult({
      last_synced_at: null,
      interval_minutes: 60,
      next_sync_at: null,
    }),
  )
  vi.mocked(useLists).mockReturnValue(queryResult([]))
  vi.mocked(useAddTrending).mockReturnValue(mutationResult(vi.fn(), false))
  vi.mocked(useServiceSettings).mockReturnValue(queryResult<ServicesSettings>(undefined))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("Trending", () => {
  it("defaults to the Trakt tab and renders the result grid", () => {
    // A second item with no TMDB id exercises the title fallback in the grid key.
    vi.mocked(useTrending).mockReturnValue(
      queryResult([ITEM, { ...ITEM, tmdb: null, title: "Severance" }]),
    )
    render(<Trending />)
    expect(screen.getByRole("tab", { name: "Trakt" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(screen.getByText("Dune")).toBeInTheDocument()
    expect(screen.getByText("Severance")).toBeInTheDocument()
    // The time-window toggle has been removed entirely (only TMDB ever supported
    // one), so it is absent on every tab.
    expect(
      screen.queryByRole("group", { name: "Time window" }),
    ).not.toBeInTheDocument()
  })

  it("changes the query when the media and category toggles are used", async () => {
    const user = userEvent.setup()
    render(<Trending />)
    await user.click(screen.getByRole("button", { name: "Shows" }))
    expect(useTrending).toHaveBeenLastCalledWith(
      expect.objectContaining({ source: "trakt", media: "show", category: "trending" }),
    )
    await user.click(screen.getByRole("button", { name: "Popular" }))
    expect(useTrending).toHaveBeenLastCalledWith(
      expect.objectContaining({ category: "popular" }),
    )
  })

  it("switches to TMDB, persists the tab and queries without a time window", async () => {
    const user = userEvent.setup()
    render(<Trending />)
    await user.click(screen.getByRole("tab", { name: "TMDB" }))
    expect(localStorage.getItem(TRENDING_TAB_STORAGE_KEY)).toBe("tmdb")
    // No time-window toggle is rendered on the TMDB tab any more, and the query
    // carries no `window` field.
    expect(
      screen.queryByRole("group", { name: "Time window" }),
    ).not.toBeInTheDocument()
    expect(useTrending).toHaveBeenLastCalledWith({
      source: "tmdb",
      media: "movie",
      category: "trending",
    })
  })

  it("restores a valid stored tab on mount", () => {
    localStorage.setItem(TRENDING_TAB_STORAGE_KEY, "seer")
    render(<Trending />)
    expect(screen.getByRole("tab", { name: "Seer" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
  })

  it("switches to the Seer tab", async () => {
    const user = userEvent.setup()
    render(<Trending />)
    await user.click(screen.getByRole("tab", { name: "Seer" }))
    expect(useTrending).toHaveBeenLastCalledWith(
      expect.objectContaining({ source: "seer" }),
    )
  })

  it("shows a loading state", () => {
    vi.mocked(useTrending).mockReturnValue(queryResult<TrendingItem[]>(undefined, true))
    render(<Trending />)
    expect(screen.getByText("Loading trending…")).toBeInTheDocument()
  })

  it("shows an empty state naming the source", () => {
    vi.mocked(useTrending).mockReturnValue(queryResult<TrendingItem[]>([]))
    render(<Trending />)
    expect(
      screen.getByText(/Nothing to show\. Check the Trakt connection/),
    ).toBeInTheDocument()
  })

  it("shows when the trending snapshot was last refreshed", () => {
    vi.mocked(useTrendingStatus).mockReturnValue(
      queryResult({
        last_synced_at: "2026-06-30T12:00:00+00:00",
        interval_minutes: 60,
        next_sync_at: "2026-06-30T13:00:00+00:00",
      }),
    )
    render(<Trending />)
    expect(screen.getByText(/^Updated/)).toBeInTheDocument()
  })

  it("hides only truly-available items and keeps pending ones when toggled", async () => {
    vi.mocked(useTrending).mockReturnValue(
      queryResult([
        ITEM, // plain discovery: stays
        // Downloaded in the library: available -> hidden.
        { ...ITEM, tmdb: 2, title: "Downloaded", in_library: true, in_library_available: true },
        // Available in Seer: hidden.
        { ...ITEM, tmdb: 3, title: "SeerAvail", seer_status: 5 },
        // Library record but media still missing: pending -> stays.
        { ...ITEM, tmdb: 4, title: "Waiting", in_library: true, in_library_available: false },
        // Processing in Seer: pending -> stays. (Title avoids the "Processing" badge text.)
        { ...ITEM, tmdb: 5, title: "Queued", seer_status: 3 },
      ]),
    )
    const user = userEvent.setup()
    render(<Trending />)
    expect(screen.getByText("Downloaded")).toBeInTheDocument()
    await user.click(screen.getByRole("switch", { name: "Hide available items" }))
    expect(screen.queryByText("Downloaded")).not.toBeInTheDocument()
    expect(screen.queryByText("SeerAvail")).not.toBeInTheDocument()
    // Pending (yellow) items survive the filter.
    expect(screen.getByText("Waiting")).toBeInTheDocument()
    expect(screen.getByText("Queued")).toBeInTheDocument()
    expect(screen.getByText("Dune")).toBeInTheDocument()
  })

  it("shows an all-available message when the filter hides every result", async () => {
    vi.mocked(useTrending).mockReturnValue(
      queryResult([{ ...ITEM, in_library: true, in_library_available: true }]),
    )
    const user = userEvent.setup()
    render(<Trending />)
    await user.click(screen.getByRole("switch", { name: "Hide available items" }))
    expect(
      screen.getByText(/Every result is already available/),
    ).toBeInTheDocument()
  })

  it("ignores a bad stored tab and survives missing localStorage", async () => {
    localStorage.setItem(TRENDING_TAB_STORAGE_KEY, "bad")
    const first = render(<Trending />)
    expect(screen.getByRole("tab", { name: "Trakt" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    first.unmount()

    vi.stubGlobal("localStorage", undefined)
    const user = userEvent.setup()
    render(<Trending />)
    await user.click(screen.getByRole("tab", { name: "Seer" }))
    expect(useTrending).toHaveBeenLastCalledWith(
      expect.objectContaining({ source: "seer" }),
    )
    // Changing the per-row density without localStorage must not throw.
    await user.click(screen.getByRole("button", { name: "7" }))
    expect(screen.getByRole("button", { name: "7" })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
  })

  it("paginates 3 rows per page (default 5 per row → 15 items)", async () => {
    vi.mocked(useTrending).mockReturnValue(queryResult(items(16)))
    const user = userEvent.setup()
    render(<Trending />)
    expect(screen.getByText("Showing 1–15 of 16")).toBeInTheDocument()
    expect(screen.getByText("Item 15")).toBeInTheDocument()
    expect(screen.queryByText("Item 16")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Next page" }))
    expect(screen.getByText("Showing 16–16 of 16")).toBeInTheDocument()
    expect(screen.getByText("Item 16")).toBeInTheDocument()
  })

  it("widens the page size when the per-row density increases (7 → 21)", async () => {
    vi.mocked(useTrending).mockReturnValue(queryResult(items(16)))
    const user = userEvent.setup()
    render(<Trending />)
    expect(screen.queryByText("Item 16")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "7" }))
    // 7 × 3 = 21 ≥ 16, so every item now fits on a single page.
    expect(screen.getByText("Item 16")).toBeInTheDocument()
    expect(screen.getByText("Showing 1–16 of 16")).toBeInTheDocument()
  })

  it("restores the stored per-row density on mount", () => {
    localStorage.setItem(TRENDING_PER_ROW_STORAGE_KEY, "7")
    vi.mocked(useTrending).mockReturnValue(queryResult(items(21)))
    render(<Trending />)
    expect(screen.getByText("Showing 1–21 of 21")).toBeInTheDocument()
    expect(screen.getByText("Item 21")).toBeInTheDocument()
  })

  it("persists the chosen per-row density to localStorage", async () => {
    vi.mocked(useTrending).mockReturnValue(queryResult(items(3)))
    const user = userEvent.setup()
    render(<Trending />)
    await user.click(screen.getByRole("button", { name: "6" }))
    expect(localStorage.getItem(TRENDING_PER_ROW_STORAGE_KEY)).toBe("6")
  })

  it("resets to page 1 when a control changes", async () => {
    vi.mocked(useTrending).mockReturnValue(queryResult(items(16)))
    const user = userEvent.setup()
    render(<Trending />)
    await user.click(screen.getByRole("button", { name: "Next page" }))
    expect(screen.getByText("Showing 16–16 of 16")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Shows" }))
    expect(screen.getByText("Showing 1–15 of 16")).toBeInTheDocument()
  })
})
