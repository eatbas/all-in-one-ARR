import { act, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useTrending: vi.fn(),
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
  useTrendingStatus,
} from "@/shared/lib/queries"
import { Trending } from "@/features/trending/Trending"
import {
  TRENDING_ANIME_SOURCE_STORAGE_KEY,
  TRENDING_PER_ROW_STORAGE_KEY,
  TRENDING_TAB_STORAGE_KEY,
} from "@/features/trending/trending-tab"
import { mutationResult, queryResult } from "@/shared/test/mock-query"
import type { ServicesSettings, TrendingItem } from "@/shared/lib/api"

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

/** A list of `n` distinct trending items titled "Item 1".."Item n". */
function items(n: number): TrendingItem[] {
  return Array.from({ length: n }, (_, index) => ({
    ...ITEM,
    tmdb: index + 1,
    title: `Item ${index + 1}`,
  }))
}

/**
 * Install a controllable `IntersectionObserver` for the current test (restored
 * by `vi.unstubAllGlobals()` in `afterEach`). The returned controls fire the most
 * recently constructed observer with an explicit intersection state. The grid
 * re-subscribes on each reveal, so firing the latest observer mirrors a real
 * scroll.
 */
function installIntersectionObserver() {
  const callbacks: IntersectionObserverCallback[] = []
  class IO {
    constructor(cb: IntersectionObserverCallback) {
      callbacks.push(cb)
    }
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
    takeRecords(): IntersectionObserverEntry[] {
      return []
    }
  }
  vi.stubGlobal(
    "IntersectionObserver",
    IO as unknown as typeof IntersectionObserver,
  )
  function notifySentinel(isIntersecting: boolean) {
    const callback = callbacks.at(-1)
    if (!callback) throw new Error("No IntersectionObserver was constructed")
    act(() => {
      callback(
        [{ isIntersecting } as IntersectionObserverEntry],
        {} as IntersectionObserver,
      )
    })
  }
  return {
    notifySentinel,
    scrollToSentinel: () => notifySentinel(true),
  }
}

/** Focus the density slider thumb and step it right `times` times (one per step). */
async function stepDensity(
  user: ReturnType<typeof userEvent.setup>,
  times = 1,
) {
  const thumb = screen.getByRole("slider", { name: "Posters per row" })
  thumb.focus()
  await user.keyboard("{ArrowRight}".repeat(times))
  return thumb
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(useTrending).mockReturnValue(queryResult([ITEM]))
  vi.mocked(useTrendingStatus).mockReturnValue(
    queryResult({
      last_synced_at: null,
      interval_minutes: 1440,
      next_sync_at: null,
    }),
  )
  vi.mocked(useLists).mockReturnValue(queryResult([]))
  vi.mocked(useAddTrending).mockReturnValue(mutationResult(vi.fn(), false))
  vi.mocked(useServiceSettings).mockReturnValue(
    queryResult<ServicesSettings>(undefined),
  )
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
    // getByTitle targets the static caption; the poster hover overlay repeats
    // the same title text, so plain text queries would match twice.
    expect(screen.getByTitle("Dune")).toBeInTheDocument()
    expect(screen.getByTitle("Severance")).toBeInTheDocument()
    // The time-window toggle has been removed entirely (only TMDB ever supported
    // one), so it is absent on every tab.
    expect(
      screen.queryByRole("group", { name: "Time window" }),
    ).not.toBeInTheDocument()
    expect(useTrending).toHaveBeenCalledTimes(1)
  })

  it("changes the query when the media and category toggles are used", async () => {
    const user = userEvent.setup()
    render(<Trending />)
    await user.click(screen.getByRole("button", { name: "Shows" }))
    expect(useTrending).toHaveBeenLastCalledWith(
      expect.objectContaining({
        source: "trakt",
        media: "show",
        category: "trending",
      }),
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

  it("opens the Anime tab on AniList shows by default and persists the tab", async () => {
    const user = userEvent.setup()
    render(<Trending />)
    await user.click(screen.getByRole("tab", { name: "Anime" }))
    expect(localStorage.getItem(TRENDING_TAB_STORAGE_KEY)).toBe("anime")
    // AniList leads the sub-source toggle, and anime defaults to shows.
    expect(useTrending).toHaveBeenLastCalledWith({
      source: "anilist",
      media: "show",
      category: "trending",
    })
  })

  it("switches and persists the anime sub-source", async () => {
    const user = userEvent.setup()
    render(<Trending />)
    await user.click(screen.getByRole("tab", { name: "Anime" }))
    const sourceToggle = screen.getByRole("group", { name: "Anime source" })
    await user.click(
      within(sourceToggle).getByRole("button", { name: "Trakt" }),
    )
    expect(localStorage.getItem(TRENDING_ANIME_SOURCE_STORAGE_KEY)).toBe(
      "trakt-anime",
    )
    expect(useTrending).toHaveBeenLastCalledWith(
      expect.objectContaining({ source: "trakt-anime", media: "show" }),
    )
    await user.click(within(sourceToggle).getByRole("button", { name: "TMDB" }))
    expect(useTrending).toHaveBeenLastCalledWith(
      expect.objectContaining({ source: "tmdb-anime" }),
    )
  })

  it("restores a stored anime sub-source and ignores a bad one", () => {
    localStorage.setItem(TRENDING_TAB_STORAGE_KEY, "anime")
    localStorage.setItem(TRENDING_ANIME_SOURCE_STORAGE_KEY, "tmdb-anime")
    const first = render(<Trending />)
    expect(useTrending).toHaveBeenLastCalledWith(
      expect.objectContaining({ source: "tmdb-anime" }),
    )
    first.unmount()

    localStorage.setItem(TRENDING_ANIME_SOURCE_STORAGE_KEY, "bad")
    render(<Trending />)
    expect(useTrending).toHaveBeenLastCalledWith(
      expect.objectContaining({ source: "anilist" }),
    )
  })

  it("shows the AniList-specific empty state without a Settings hint", () => {
    vi.mocked(useTrending).mockReturnValue(queryResult<TrendingItem[]>([]))
    localStorage.setItem(TRENDING_TAB_STORAGE_KEY, "anime")
    render(<Trending />)
    expect(
      screen.getByText(/AniList may be temporarily unavailable/),
    ).toBeInTheDocument()
    expect(screen.queryByText(/connection in Settings/)).not.toBeInTheDocument()
  })

  it("shows a loading state", () => {
    vi.mocked(useTrending).mockReturnValue(
      queryResult<TrendingItem[]>(undefined, true),
    )
    render(<Trending />)
    expect(screen.getByText("Loading trending…")).toBeInTheDocument()
  })

  it("keeps cached rows visible during a background refresh", () => {
    vi.mocked(useTrending).mockReturnValue(
      queryResult([ITEM], false, { isFetching: true }),
    )
    render(<Trending />)
    expect(screen.getByTitle("Dune")).toBeInTheDocument()
    expect(screen.queryByText("Loading trending…")).not.toBeInTheDocument()
    expect(screen.getByText("Refreshing")).toBeInTheDocument()
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
        {
          ...ITEM,
          tmdb: 2,
          title: "Downloaded",
          in_library: true,
          in_library_available: true,
        },
        // Available in Seer: hidden.
        { ...ITEM, tmdb: 3, title: "SeerAvail", seer_status: 5 },
        // Library record but media still missing: pending -> stays.
        {
          ...ITEM,
          tmdb: 4,
          title: "Waiting",
          in_library: true,
          in_library_available: false,
        },
        // Processing in Seer: pending -> stays.
        { ...ITEM, tmdb: 5, title: "Queued", seer_status: 3 },
      ]),
    )
    const user = userEvent.setup()
    render(<Trending />)
    expect(screen.getByTitle("Downloaded")).toBeInTheDocument()
    await user.click(
      screen.getByRole("switch", { name: "Hide available items" }),
    )
    expect(screen.queryByTitle("Downloaded")).not.toBeInTheDocument()
    expect(screen.queryByTitle("SeerAvail")).not.toBeInTheDocument()
    // Pending (amber) items survive the filter.
    expect(screen.getByTitle("Waiting")).toBeInTheDocument()
    expect(screen.getByTitle("Queued")).toBeInTheDocument()
    expect(screen.getByTitle("Dune")).toBeInTheDocument()
  })

  it("shows an all-available message when the filter hides every result", async () => {
    vi.mocked(useTrending).mockReturnValue(
      queryResult([{ ...ITEM, in_library: true, in_library_available: true }]),
    )
    const user = userEvent.setup()
    render(<Trending />)
    await user.click(
      screen.getByRole("switch", { name: "Hide available items" }),
    )
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
    const thumb = await stepDensity(user)
    expect(thumb).toHaveAttribute("aria-valuenow", "6")
  })

  it("survives missing localStorage on the anime tab", async () => {
    vi.stubGlobal("localStorage", undefined)
    const user = userEvent.setup()
    render(<Trending />)
    // Mounting the anime panel reads the stored source; switching the source
    // writes it back — neither may throw when localStorage is unavailable.
    await user.click(screen.getByRole("tab", { name: "Anime" }))
    await user.click(screen.getByRole("button", { name: "Trakt" }))
    expect(useTrending).toHaveBeenLastCalledWith(
      expect.objectContaining({ source: "trakt-anime" }),
    )
  })

  it("survives throwing localStorage access and methods", async () => {
    const original = Object.getOwnPropertyDescriptor(window, "localStorage")
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get: () => {
        throw new DOMException("Storage disabled", "SecurityError")
      },
    })
    const user = userEvent.setup()
    try {
      render(<Trending />)
      // The default tab and density load without throwing.
      expect(screen.getByRole("tab", { name: "Trakt" })).toHaveAttribute(
        "aria-selected",
        "true",
      )
      await user.click(screen.getByRole("tab", { name: "Seer" }))
      expect(useTrending).toHaveBeenLastCalledWith(
        expect.objectContaining({ source: "seer" }),
      )
      const thumb = await stepDensity(user)
      expect(thumb).toHaveAttribute("aria-valuenow", "6")
    } finally {
      if (original) Object.defineProperty(window, "localStorage", original)
    }
  })

  it("survives throwing getItem and setItem", async () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new DOMException("Storage denied", "SecurityError")
      },
      setItem: () => {
        throw new DOMException("Quota exceeded", "QuotaExceededError")
      },
    })
    const user = userEvent.setup()
    render(<Trending />)
    await user.click(screen.getByRole("tab", { name: "Anime" }))
    await user.click(screen.getByRole("button", { name: "Trakt" }))
    expect(useTrending).toHaveBeenLastCalledWith(
      expect.objectContaining({ source: "trakt-anime" }),
    )
    const thumb = await stepDensity(user)
    expect(thumb).toHaveAttribute("aria-valuenow", "6")
  })

  it("reveals the first three rows then loads three more on scroll", async () => {
    vi.mocked(useTrending).mockReturnValue(queryResult(items(16)))
    const scroll = installIntersectionObserver()
    render(<Trending />)
    // Default 5 per row × 3 rows = 15 items shown; the 16th waits below the fold.
    expect(screen.getByTitle("Item 15")).toBeInTheDocument()
    expect(screen.queryByTitle("Item 16")).not.toBeInTheDocument()
    // The sentinel is present while rows remain below the fold.
    expect(screen.getByTestId("trending-scroll-sentinel")).toBeInTheDocument()
    scroll.scrollToSentinel()
    expect(screen.getByTitle("Item 16")).toBeInTheDocument()
    // With every row revealed the sentinel unmounts, so no further loads fire.
    expect(
      screen.queryByTestId("trending-scroll-sentinel"),
    ).not.toBeInTheDocument()
  })

  it("does not reveal more rows while the sentinel is outside the viewport", () => {
    vi.mocked(useTrending).mockReturnValue(queryResult(items(16)))
    const observer = installIntersectionObserver()
    render(<Trending />)

    observer.notifySentinel(false)

    expect(screen.queryByTitle("Item 16")).not.toBeInTheDocument()
    expect(screen.getByTestId("trending-scroll-sentinel")).toBeInTheDocument()
  })

  it("widens the first batch when the per-row density increases (7 → 21)", async () => {
    vi.mocked(useTrending).mockReturnValue(queryResult(items(16)))
    const user = userEvent.setup()
    render(<Trending />)
    expect(screen.queryByTitle("Item 16")).not.toBeInTheDocument()
    // Step the slider 5 → 7; 7 × 3 = 21 ≥ 16, so every item now fits the batch.
    await stepDensity(user, 2)
    expect(screen.getByTitle("Item 16")).toBeInTheDocument()
  })

  it("restores the stored per-row density on mount", () => {
    localStorage.setItem(TRENDING_PER_ROW_STORAGE_KEY, "7")
    vi.mocked(useTrending).mockReturnValue(queryResult(items(21)))
    render(<Trending />)
    // 7 × 3 = 21, so the whole list is in the first batch — no scroll needed.
    expect(screen.getByTitle("Item 1")).toBeInTheDocument()
    expect(screen.getByTitle("Item 21")).toBeInTheDocument()
  })

  it("ignores an invalid stored per-row density and falls back to the default", () => {
    localStorage.setItem(TRENDING_PER_ROW_STORAGE_KEY, "99")
    vi.mocked(useTrending).mockReturnValue(queryResult(items(16)))
    render(<Trending />)
    // Default 5 × 3 = 15, so the 16th item is outside the first batch.
    expect(screen.getByTitle("Item 15")).toBeInTheDocument()
    expect(screen.queryByTitle("Item 16")).not.toBeInTheDocument()
  })

  it("exposes the density control as a labelled slider, not a pager", () => {
    render(<Trending />)
    expect(
      screen.getByRole("slider", { name: "Posters per row" }),
    ).toBeInTheDocument()
    // The old pager copy must be gone from this page.
    expect(screen.queryByText(/^Showing /)).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Next page" }),
    ).not.toBeInTheDocument()
  })

  it("persists the chosen per-row density to localStorage", async () => {
    vi.mocked(useTrending).mockReturnValue(queryResult(items(3)))
    const user = userEvent.setup()
    render(<Trending />)
    await stepDensity(user)
    expect(localStorage.getItem(TRENDING_PER_ROW_STORAGE_KEY)).toBe("6")
  })

  it("collapses the reveal back to the first batch when a control changes", async () => {
    vi.mocked(useTrending).mockReturnValue(queryResult(items(16)))
    const scroll = installIntersectionObserver()
    const user = userEvent.setup()
    render(<Trending />)
    scroll.scrollToSentinel()
    expect(screen.getByTitle("Item 16")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Shows" }))
    // Back to the first three rows: the 16th item is hidden again.
    expect(screen.queryByTitle("Item 16")).not.toBeInTheDocument()
    expect(screen.getByTitle("Item 15")).toBeInTheDocument()
  })

  it("collapses the reveal when the hide-available toggle changes", async () => {
    vi.mocked(useTrending).mockReturnValue(queryResult(items(16)))
    const scroll = installIntersectionObserver()
    const user = userEvent.setup()
    render(<Trending />)
    scroll.scrollToSentinel()
    expect(screen.getByTitle("Item 16")).toBeInTheDocument()
    // Every item here is unavailable, so the toggle filters nothing out — it
    // isolates the reveal reset in changeHideAvailable.
    await user.click(
      screen.getByRole("switch", { name: "Hide available items" }),
    )
    expect(screen.queryByTitle("Item 16")).not.toBeInTheDocument()
    expect(screen.getByTitle("Item 15")).toBeInTheDocument()
  })
})
