import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useLists: vi.fn(),
  useListItems: vi.fn(),
  useItems: vi.fn(),
  useTraktSettings: vi.fn(),
  useTraktLists: vi.fn(),
  useAddTraktList: vi.fn(),
  useRemoveTraktList: vi.fn(),
}))

import {
  useAddTraktList,
  useItems,
  useListItems,
  useLists,
  useRemoveTraktList,
  useTraktLists,
  useTraktSettings,
} from "@/shared/lib/queries"
import { ListSyncarr } from "@/features/list-syncarr/ListSyncarr"
import { LIST_SYNCARR_TAB_STORAGE_KEY } from "@/features/list-syncarr/list-syncarr-tab"
import type { Item, ListSummary, TraktSettings } from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"

/** Build a mutation-shaped stub; typed loosely as these are test doubles. */
function mutation(mutate: unknown, isPending = false) {
  return { mutate, isPending } as never
}

const TRAKT_SETTINGS: TraktSettings = {
  client_id_hint: "1234",
  client_id_set: true,
  client_secret_set: true,
  connected: true,
  lists: [],
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(useLists).mockReturnValue(queryResult<ListSummary[]>([], false))
  vi.mocked(useListItems).mockReturnValue(queryResult<Item[]>([], false))
  vi.mocked(useItems).mockReturnValue(queryResult<Item[]>([], false))
  vi.mocked(useTraktSettings).mockReturnValue(queryResult(TRAKT_SETTINGS))
  vi.mocked(useTraktLists).mockReturnValue(queryResult([], false))
  vi.mocked(useAddTraktList).mockReturnValue(mutation(vi.fn()))
  vi.mocked(useRemoveTraktList).mockReturnValue(mutation(vi.fn()))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("ListSyncarr", () => {
  it("defaults to the Lists tab", () => {
    render(<ListSyncarr />)
    expect(screen.getByRole("tab", { name: "Lists" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(
      screen.getByText("Trakt lists kept in sync by the engine."),
    ).toBeInTheDocument()
  })

  it("switches to the Settings tab and shows the list controls", async () => {
    const user = userEvent.setup()
    render(<ListSyncarr />)
    await user.click(screen.getByRole("tab", { name: "Settings" }))
    expect(localStorage.getItem(LIST_SYNCARR_TAB_STORAGE_KEY)).toBe("settings")
    expect(
      screen.getByText("Choose which Trakt lists the engine keeps in sync."),
    ).toBeInTheDocument()
  })

  it("restores the Items tab from localStorage", () => {
    localStorage.setItem(LIST_SYNCARR_TAB_STORAGE_KEY, "items")
    render(<ListSyncarr />)
    expect(screen.getByRole("tab", { name: "Items" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(
      screen.getByText("Every movie and show mirrored from Trakt."),
    ).toBeInTheDocument()
  })

  it("ignores an unknown stored tab and falls back to Lists", () => {
    localStorage.setItem(LIST_SYNCARR_TAB_STORAGE_KEY, "bogus")
    render(<ListSyncarr />)
    expect(screen.getByRole("tab", { name: "Lists" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
  })

  it("persists the selected tab to localStorage on change", async () => {
    const user = userEvent.setup()
    render(<ListSyncarr />)
    await user.click(screen.getByRole("tab", { name: "Items" }))
    expect(localStorage.getItem(LIST_SYNCARR_TAB_STORAGE_KEY)).toBe("items")
    expect(
      screen.getByText("Every movie and show mirrored from Trakt."),
    ).toBeInTheDocument()
  })

  it("stays usable when localStorage is unavailable", async () => {
    vi.stubGlobal("localStorage", undefined)
    const user = userEvent.setup()
    render(<ListSyncarr />)
    // Falls back to the Lists default without throwing.
    expect(screen.getByRole("tab", { name: "Lists" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    // Switching still works; the persistence write is safely skipped.
    await user.click(screen.getByRole("tab", { name: "Items" }))
    expect(
      screen.getByText("Every movie and show mirrored from Trakt."),
    ).toBeInTheDocument()
  })
})
