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
import type { Item, ListSummary, ServicesSettings, Status } from "@/shared/lib/api"
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
    vi.mocked(useStatus).mockReturnValue(queryResult<Status>(undefined, false))
    vi.mocked(useLists).mockReturnValue(queryResult(lists))
    vi.mocked(useListItems).mockReturnValue(queryResult(items))
    vi.mocked(useServiceSettings).mockReturnValue(queryResult(SERVICES))
    vi.mocked(useRemoveItem).mockReturnValue(mutation(removeItemMutate))
    vi.mocked(useRemoveAvailable).mockReturnValue(mutation(removeAvailableMutate))
    vi.mocked(useSyncNow).mockReturnValue(mutation(syncNowMutate))
  })

  it("renders the sync-engine stat cards between the Lists heading and the synced lists card", () => {
    render(<Lists />)
    expect(screen.getByText("Synced")).toBeInTheDocument()
    expect(screen.getByText("Requested")).toBeInTheDocument()
    expect(screen.getByText("Available")).toBeInTheDocument()
    expect(screen.getByText("Removed")).toBeInTheDocument()
  })

  it("shows a loading message while the lists query is pending", () => {
    vi.mocked(useLists).mockReturnValue(queryResult<ListSummary[]>(undefined, true))
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
    // The availability pill is overlaid on each poster with its full status name.
    expect(
      screen.getByText("Available", { selector: "[data-slot='badge']" }),
    ).toBeInTheDocument()
    expect(
      screen.getByText("Requested", { selector: "[data-slot='badge']" }),
    ).toBeInTheDocument()
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
    vi.mocked(useListItems).mockReturnValue(queryResult<Item[]>(undefined, true))
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
    vi.mocked(useListItems).mockReturnValue(queryResult<Item[]>(undefined, false))
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
      screen.queryByText("Removed", { selector: "[data-slot='badge']" }),
    ).not.toBeInTheDocument()
    expect(screen.getByText("This list has no items yet.")).toBeInTheDocument()
  })

  it("reveals removed items (without a delete control) when 'Show removed' is on", async () => {
    vi.mocked(useListItems).mockReturnValue(queryResult<Item[]>([removedItem]))
    const user = userEvent.setup()
    render(<Lists />)

    await user.click(screen.getByRole("switch", { name: "Show removed items" }))
    await user.click(screen.getByRole("button", { name: /Movies/ }))
    // The removed item now renders (with its status pill) but offers no delete.
    expect(
      screen.getByText("Removed", { selector: "[data-slot='badge']" }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: 'Remove "Gone" from the list' }),
    ).not.toBeInTheDocument()
  })
})
