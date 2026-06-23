import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useLists: vi.fn(),
  useListItems: vi.fn(),
  useItems: vi.fn(),
}))

import { useItems, useListItems, useLists } from "@/shared/lib/queries"
import { ListSyncarr } from "@/features/list-syncarr/ListSyncarr"
import { LIST_SYNCARR_TAB_STORAGE_KEY } from "@/features/list-syncarr/list-syncarr-tab"
import type { Item, ListSummary } from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"

beforeEach(() => {
  localStorage.clear()
  vi.mocked(useLists).mockReturnValue(queryResult<ListSummary[]>([], false))
  vi.mocked(useListItems).mockReturnValue(queryResult<Item[]>([], false))
  vi.mocked(useItems).mockReturnValue(queryResult<Item[]>([], false))
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
