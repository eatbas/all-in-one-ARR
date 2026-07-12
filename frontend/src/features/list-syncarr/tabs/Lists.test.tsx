import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useStatus: vi.fn(),
  useLists: vi.fn(),
  useListItems: vi.fn(),
  useServiceSettings: vi.fn(),
  useRemoveItem: vi.fn(),
  useRemoveAvailable: vi.fn(),
  useSyncNow: vi.fn(),
}))

import {
  useLists,
  useListItems,
  useRemoveAvailable,
  useRemoveItem,
  useServiceSettings,
  useStatus,
  useSyncNow,
} from "@/shared/lib/queries"

import { Lists } from "@/features/list-syncarr/tabs/Lists"
import {
  DEFAULT_LIST_SYNCARR_PER_ROW,
  LIST_SYNCARR_PER_ROW_STORAGE_KEY,
} from "@/features/list-syncarr/list-syncarr-tab"
import type {
  Item,
  ListSummary,
  ServicesSettings,
  Status,
} from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"

const SERVICES: ServicesSettings = {
  seer: { url: "https://requests.example.com", api_key_set: true },
  sonarr: { url: "", api_key_set: false },
  radarr: { url: "", api_key_set: false },
  tmdb: { api_key_set: false },
  omdb: { api_key_set: false },
  sabnzbd: { url: "", api_key_set: false },
  qbittorrent: { url: "", api_key_set: false },
}

const lists: ListSummary[] = [
  {
    owner_user: "me",
    slug: "movies",
    name: "Movies",
    item_count: 19,
    removed_count: 0,
    // Far in the past relative to any test run, so the derived strings are stable.
    last_synced_at: "2024-06-01T11:15:00Z",
    next_sync_at: "2024-06-01T12:30:00Z",
    interval_minutes: 15,
  },
  {
    owner_user: "me",
    slug: "tv",
    name: "TV",
    // All six items are removed, so the active count is zero: "(0)" / "(0 + 6)".
    item_count: 6,
    removed_count: 6,
    last_synced_at: null,
    next_sync_at: null,
    interval_minutes: 15,
  },
]

const itemBase = {
  tvdb: null,
  imdb: null,
  seer_request_id: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
} as const

const items: Item[] = [
  {
    ...itemBase,
    trakt_id: 1,
    list_id: "movies",
    title: "Dune",
    year: 2021,
    type: "movie",
    tmdb: 438631,
    status: "available",
  },
  {
    ...itemBase,
    trakt_id: 2,
    list_id: "movies",
    title: "NoPoster",
    year: null,
    type: "movie",
    tmdb: null,
    status: "requested",
  },
]

/** Build a mutation-shaped stub; typed loosely as these are test doubles. */
function mutation(mutate: unknown, isPending = false) {
  return { mutate, isPending } as never
}

describe("Lists page", () => {
  let removeItemMutate: ReturnType<typeof vi.fn>
  let removeAvailableMutate: ReturnType<typeof vi.fn>
  let syncNowMutate: ReturnType<typeof vi.fn>

  beforeEach(() => {
    removeItemMutate = vi.fn()
    removeAvailableMutate = vi.fn()
    syncNowMutate = vi.fn()
    localStorage.clear()
    vi.mocked(useStatus).mockReturnValue(queryResult<Status>(undefined, false))
    vi.mocked(useLists).mockReturnValue(queryResult(lists))
    vi.mocked(useListItems).mockReturnValue(queryResult(items))
    vi.mocked(useServiceSettings).mockReturnValue(queryResult(SERVICES))
    vi.mocked(useRemoveItem).mockReturnValue(mutation(removeItemMutate))
    vi.mocked(useRemoveAvailable).mockReturnValue(
      mutation(removeAvailableMutate),
    )
    vi.mocked(useSyncNow).mockReturnValue(mutation(syncNowMutate))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("renders the sync-engine stat cards between the Lists heading and the synced lists card", () => {
    render(<Lists />)
    expect(screen.getByText("Synced")).toBeInTheDocument()
    expect(screen.getByText("Requested")).toBeInTheDocument()
    expect(screen.getByText("Available")).toBeInTheDocument()
    expect(screen.getByText("Removed")).toBeInTheDocument()
  })

  it("shows a loading message while the lists query is pending", () => {
    vi.mocked(useLists).mockReturnValue(
      queryResult<ListSummary[]>(undefined, true),
    )
    render(<Lists />)
    expect(screen.getByText("Loading lists…")).toBeInTheDocument()
  })

  it("shows an empty message when no lists are selected", () => {
    vi.mocked(useLists).mockReturnValue(queryResult<ListSummary[]>([], false))
    render(<Lists />)
    expect(screen.getByText("No lists selected yet.")).toBeInTheDocument()
  })

  it("treats undefined data as empty once the query has settled", () => {
    vi.mocked(useLists).mockReturnValue(
      queryResult<ListSummary[]>(undefined, false),
    )
    render(<Lists />)
    expect(screen.getByText("No lists selected yet.")).toBeInTheDocument()
  })

  it("renders each list with its count and sync timing", () => {
    render(<Lists />)
    expect(screen.getByText("Movies")).toBeInTheDocument()
    expect(screen.getByText("(19)")).toBeInTheDocument()
    expect(screen.getByText("TV")).toBeInTheDocument()
    expect(screen.getByText("(0)")).toBeInTheDocument()
    // The never-synced list shows fallbacks for both timestamps.
    expect(screen.getByText(/last synced: never/)).toBeInTheDocument()
    expect(screen.getByText(/next sync —/)).toBeInTheDocument()
  })

  it("shows the active+removed split once 'Show removed' is enabled", async () => {
    const user = userEvent.setup()
    render(<Lists />)

    // Default view counts only active items.
    expect(screen.getByText("(19)")).toBeInTheDocument()
    expect(screen.getByText("(0)")).toBeInTheDocument()

    await user.click(screen.getByRole("switch", { name: "Show removed items" }))

    // The header now spells out "active + removed" for each list.
    expect(screen.getByText("(19 + 0)")).toBeInTheDocument()
    expect(screen.getByText("(0 + 6)")).toBeInTheDocument()
  })

  it("triggers a manual sync when 'Sync now' is clicked", async () => {
    const user = userEvent.setup()
    render(<Lists />)

    await user.click(screen.getByRole("button", { name: "Sync now" }))
    expect(syncNowMutate).toHaveBeenCalled()
  })

  it("disables 'Sync now' and spins its icon while a sync is in flight", () => {
    vi.mocked(useSyncNow).mockReturnValue(mutation(syncNowMutate, true))
    render(<Lists />)

    const button = screen.getByRole("button", { name: "Sync now" })
    expect(button).toBeDisabled()
    expect(button.querySelector("svg")).toHaveClass("animate-spin")
  })

  it("counts the next sync down each minute without a page refresh", () => {
    vi.useFakeTimers()
    try {
      vi.setSystemTime(new Date("2024-06-01T12:00:00Z"))
      vi.mocked(useLists).mockReturnValue(
        queryResult<ListSummary[]>([
          { ...lists[0], next_sync_at: "2024-06-01T12:03:00Z" },
        ]),
      )
      render(<Lists />)
      expect(screen.getByText(/next sync in 3 min/)).toBeInTheDocument()

      // One minute later the label has ticked down on its own.
      act(() => {
        vi.advanceTimersByTime(60_000)
      })
      expect(screen.getByText(/next sync in 2 min/)).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("expands a row to reveal posters, titles, meta and statuses", async () => {
    const user = userEvent.setup()
    render(<Lists />)

    await user.click(screen.getByRole("button", { name: /Movies/ }))

    // The item with a TMDB id renders an image poster.
    expect(screen.getByRole("img", { name: "Dune" })).toHaveAttribute(
      "src",
      "/api/posters/movie/438631",
    )
    // The item without a TMDB id falls back to a placeholder.
    expect(
      screen.getByRole("img", { name: "No poster for NoPoster" }),
    ).toBeInTheDocument()
    // Each card shows a "year · type" meta row; a missing year falls back to "—".
    // (CSS `capitalize` does not change textContent, so the type stays lowercase.)
    expect(screen.getByText("2021 · movie")).toBeInTheDocument()
    expect(screen.getByText("— · movie")).toBeInTheDocument()
    // The status pill is overlaid on each poster; the precise status lives in
    // its aria-label while the visible hover word stays collapsed.
    expect(screen.getByLabelText("Available")).toBeInTheDocument()
    expect(screen.getByLabelText("Requested")).toBeInTheDocument()
    // The item with a TMDB id links to its Seer request page.
    expect(
      screen.getByRole("link", { name: 'Request "Dune" in Seer' }),
    ).toHaveAttribute("href", "https://requests.example.com/movie/438631")
    // The item without a TMDB id cannot be deep-linked, so it shows no link.
    expect(screen.getAllByRole("link")).toHaveLength(1)
  })

  it("omits the request link when Seer is not configured", async () => {
    vi.mocked(useServiceSettings).mockReturnValue(
      queryResult<ServicesSettings>(undefined, false),
    )
    const user = userEvent.setup()
    render(<Lists />)

    await user.click(screen.getByRole("button", { name: /Movies/ }))
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
  })

  it("shows a loading message while a list's items load", async () => {
    vi.mocked(useListItems).mockReturnValue(
      queryResult<Item[]>(undefined, true),
    )
    const user = userEvent.setup()
    render(<Lists />)

    await user.click(screen.getByRole("button", { name: /Movies/ }))
    expect(screen.getByText("Loading items…")).toBeInTheDocument()
  })

  it("shows an empty message when an expanded list has no items", async () => {
    vi.mocked(useListItems).mockReturnValue(queryResult<Item[]>([], false))
    const user = userEvent.setup()
    render(<Lists />)

    await user.click(screen.getByRole("button", { name: /Movies/ }))
    expect(screen.getByText("This list has no items yet.")).toBeInTheDocument()
  })

  it("treats settled-but-undefined items as empty", async () => {
    vi.mocked(useListItems).mockReturnValue(
      queryResult<Item[]>(undefined, false),
    )
    const user = userEvent.setup()
    render(<Lists />)

    await user.click(screen.getByRole("button", { name: /Movies/ }))
    expect(screen.getByText("This list has no items yet.")).toBeInTheDocument()
  })

  it("removes all available items after confirming the bulk action", async () => {
    const user = userEvent.setup()
    render(<Lists />)

    await user.click(screen.getByRole("button", { name: "Delete availables" }))
    // The confirmation dialog appears; cancelling first does nothing.
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    expect(removeAvailableMutate).not.toHaveBeenCalled()

    await user.click(screen.getByRole("button", { name: "Delete availables" }))
    await user.click(screen.getByRole("button", { name: "Delete" }))
    expect(removeAvailableMutate).toHaveBeenCalled()
  })

  it("removes a single item after confirming on its thumbnail", async () => {
    const user = userEvent.setup()
    render(<Lists />)

    await user.click(screen.getByRole("button", { name: /Movies/ }))
    await user.click(
      screen.getByRole("button", { name: 'Remove "Dune" from the list' }),
    )
    await user.click(screen.getByRole("button", { name: "Remove" }))
    expect(removeItemMutate).toHaveBeenCalledWith({
      list_id: "movies",
      trakt_id: 1,
    })
  })

  it("carries a hover-revealed Remove label on the delete pill", async () => {
    const user = userEvent.setup()
    render(<Lists />)

    await user.click(screen.getByRole("button", { name: /Movies/ }))
    // The word is always in the DOM (collapsed via max-width until hover or
    // keyboard focus), so the pill expands like the Trending overlay pills.
    const deleteButton = screen.getByRole("button", {
      name: 'Remove "Dune" from the list',
    })
    expect(deleteButton).toHaveTextContent("Remove")
  })

  it("keeps a visible keyboard-focus ring on the delete pill", async () => {
    const user = userEvent.setup()
    render(<Lists />)

    await user.click(screen.getByRole("button", { name: /Movies/ }))
    // The pill shell strips the browser's default outline, and the icon-only
    // delete pill has no hover-reveal label, so it must carry its own
    // focus-visible ring for keyboard users.
    const deleteButton = screen.getByRole("button", {
      name: 'Remove "Dune" from the list',
    })
    expect(deleteButton).toHaveClass(
      "focus-visible:ring-[3px]",
      "focus-visible:ring-ring/50",
    )
  })

  const removedItem: Item = {
    ...itemBase,
    trakt_id: 9,
    list_id: "movies",
    title: "Gone",
    year: 2000,
    type: "movie",
    tmdb: 111,
    status: "removed",
  }

  it("hides already-removed items until 'Show removed' is enabled", async () => {
    vi.mocked(useListItems).mockReturnValue(queryResult<Item[]>([removedItem]))
    const user = userEvent.setup()
    render(<Lists />)

    // By default the removed item is hidden, so the expanded list looks empty.
    await user.click(screen.getByRole("button", { name: /Movies/ }))
    expect(
      screen.queryByLabelText("Removed from the list"),
    ).not.toBeInTheDocument()
    expect(screen.getByText("This list has no items yet.")).toBeInTheDocument()
  })

  it("sorts the item grid by status, with removed items at the bottom", async () => {
    // Supplied deliberately out of order; the grid must render
    // available -> requested -> synced -> removed.
    const mixed: Item[] = [
      {
        ...itemBase,
        trakt_id: 10,
        list_id: "movies",
        title: "Zeta",
        year: 2000,
        type: "movie",
        tmdb: 10,
        status: "removed",
      },
      {
        ...itemBase,
        trakt_id: 11,
        list_id: "movies",
        title: "Yan",
        year: 2000,
        type: "movie",
        tmdb: 11,
        status: "synced",
      },
      {
        ...itemBase,
        trakt_id: 12,
        list_id: "movies",
        title: "Xavier",
        year: 2000,
        type: "movie",
        tmdb: 12,
        status: "available",
      },
      {
        ...itemBase,
        trakt_id: 13,
        list_id: "movies",
        title: "Wendy",
        year: 2000,
        type: "movie",
        tmdb: 13,
        status: "requested",
      },
    ]
    vi.mocked(useListItems).mockReturnValue(queryResult<Item[]>(mixed))
    const user = userEvent.setup()
    render(<Lists />)

    await user.click(screen.getByRole("switch", { name: "Show removed items" }))
    await user.click(screen.getByRole("button", { name: /Movies/ }))

    // Ordering is read from the pills' aria-labels (the precise status words);
    // visible reveal labels stay in the DOM even when collapsed, so text
    // queries would be ambiguous here.
    const pills = screen.getAllByLabelText(
      /^(Available|Requested|Synced from Trakt|Removed from the list)$/,
    )
    expect(pills.map((pill) => pill.getAttribute("aria-label"))).toEqual([
      "Available",
      "Requested",
      "Synced from Trakt",
      "Removed from the list",
    ])
  })

  it("reveals removed items (without a delete control) when 'Show removed' is on", async () => {
    vi.mocked(useListItems).mockReturnValue(queryResult<Item[]>([removedItem]))
    const user = userEvent.setup()
    render(<Lists />)

    await user.click(screen.getByRole("switch", { name: "Show removed items" }))
    await user.click(screen.getByRole("button", { name: /Movies/ }))
    // The removed item now renders (with its status pill) but offers no delete.
    expect(screen.getByLabelText("Removed from the list")).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: 'Remove "Gone" from the list' }),
    ).not.toBeInTheDocument()
  })

  it("exposes the density control as a labelled slider", () => {
    render(<Lists />)
    expect(
      screen.getByRole("slider", { name: "Posters per row" }),
    ).toBeInTheDocument()
  })

  it("defaults to the ListSyncarr density of 8", async () => {
    const user = userEvent.setup()
    render(<Lists />)
    await user.click(screen.getByRole("button", { name: /Movies/ }))

    const grid = screen.getByTestId("list-syncarr-grid")
    expect(grid).toHaveClass("lg:grid-cols-8")
    // Density 8 uses a 22px pill shell.
    expect(
      screen.getByRole("button", { name: 'Remove "Dune" from the list' }),
    ).toHaveClass("h-[22px]")
  })

  it("updates the grid and every overlay density when the slider changes", async () => {
    const user = userEvent.setup()
    render(<Lists />)
    await user.click(screen.getByRole("button", { name: /Movies/ }))

    const thumb = screen.getByRole("slider", { name: "Posters per row" })
    thumb.focus()
    // Step from the default 8 down to 5.
    await user.keyboard("{ArrowLeft}".repeat(3))

    expect(thumb).toHaveAttribute("aria-valuenow", "5")
    const grid = screen.getByTestId("list-syncarr-grid")
    expect(grid).toHaveClass("lg:grid-cols-5")
    expect(grid).not.toHaveClass("lg:grid-cols-8")
    // Density 5 uses the largest pill shell.
    expect(
      screen.getByRole("button", { name: 'Remove "Dune" from the list' }),
    ).toHaveClass("h-8")
    expect(screen.getByLabelText("Available")).toHaveClass("h-8")
    // The Seer link overlay also scales with density.
    expect(
      screen.getByRole("link", { name: 'Request "Dune" in Seer' }),
    ).toHaveClass("h-8")
  })

  it("persists the chosen density to localStorage", async () => {
    const user = userEvent.setup()
    render(<Lists />)
    const thumb = screen.getByRole("slider", { name: "Posters per row" })
    thumb.focus()
    await user.keyboard("{ArrowRight}")
    expect(localStorage.getItem(LIST_SYNCARR_PER_ROW_STORAGE_KEY)).toBe("9")
  })

  it("restores a valid stored density on mount", async () => {
    localStorage.setItem(LIST_SYNCARR_PER_ROW_STORAGE_KEY, "6")
    const user = userEvent.setup()
    render(<Lists />)
    await user.click(screen.getByRole("button", { name: /Movies/ }))

    const grid = screen.getByTestId("list-syncarr-grid")
    expect(grid).toHaveClass("lg:grid-cols-6")
    expect(
      screen.getByRole("button", { name: 'Remove "Dune" from the list' }),
    ).toHaveClass("h-7")
  })

  it("restores density, grid, and all overlay classes after unmount/remount", async () => {
    const user = userEvent.setup()
    const { unmount } = render(<Lists />)
    await user.click(screen.getByRole("button", { name: /Movies/ }))

    const thumb = screen.getByRole("slider", { name: "Posters per row" })
    thumb.focus()
    // Step from the default 8 down to 5.
    await user.keyboard("{ArrowLeft}".repeat(3))
    expect(thumb).toHaveAttribute("aria-valuenow", "5")
    unmount()

    render(<Lists />)
    await user.click(screen.getByRole("button", { name: /Movies/ }))

    const restoredThumb = screen.getByRole("slider", {
      name: "Posters per row",
    })
    expect(restoredThumb).toHaveAttribute("aria-valuenow", "5")
    const grid = screen.getByTestId("list-syncarr-grid")
    expect(grid).toHaveClass("lg:grid-cols-5")
    expect(
      screen.getByRole("button", { name: 'Remove "Dune" from the list' }),
    ).toHaveClass("h-8")
    expect(screen.getByLabelText("Available")).toHaveClass("h-8")
    expect(
      screen.getByRole("link", { name: 'Request "Dune" in Seer' }),
    ).toHaveClass("h-8")
  })

  it("falls back to the default for an invalid stored density", async () => {
    localStorage.setItem(LIST_SYNCARR_PER_ROW_STORAGE_KEY, "99")
    const user = userEvent.setup()
    render(<Lists />)
    await user.click(screen.getByRole("button", { name: /Movies/ }))

    const grid = screen.getByTestId("list-syncarr-grid")
    expect(grid).toHaveClass(`lg:grid-cols-${DEFAULT_LIST_SYNCARR_PER_ROW}`)
  })

  it("falls back to the default when localStorage is unavailable", async () => {
    vi.stubGlobal("localStorage", undefined)
    const user = userEvent.setup()
    render(<Lists />)
    await user.click(screen.getByRole("button", { name: /Movies/ }))

    const grid = screen.getByTestId("list-syncarr-grid")
    expect(grid).toHaveClass(`lg:grid-cols-${DEFAULT_LIST_SYNCARR_PER_ROW}`)
    // Interacting with the slider must not throw without storage.
    const thumb = screen.getByRole("slider", { name: "Posters per row" })
    thumb.focus()
    await expect(user.keyboard("{ArrowRight}")).resolves.toBeUndefined()
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
      render(<Lists />)
      await user.click(screen.getByRole("button", { name: /Movies/ }))

      const grid = screen.getByTestId("list-syncarr-grid")
      expect(grid).toHaveClass(`lg:grid-cols-${DEFAULT_LIST_SYNCARR_PER_ROW}`)
      const thumb = screen.getByRole("slider", { name: "Posters per row" })
      thumb.focus()
      await expect(user.keyboard("{ArrowRight}")).resolves.toBeUndefined()
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
    render(<Lists />)
    await user.click(screen.getByRole("button", { name: /Movies/ }))

    const grid = screen.getByTestId("list-syncarr-grid")
    expect(grid).toHaveClass(`lg:grid-cols-${DEFAULT_LIST_SYNCARR_PER_ROW}`)
    const thumb = screen.getByRole("slider", { name: "Posters per row" })
    thumb.focus()
    await expect(user.keyboard("{ArrowRight}")).resolves.toBeUndefined()
  })
})
