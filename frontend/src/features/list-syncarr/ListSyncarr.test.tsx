import { render as rtlRender, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useStatus: vi.fn(),
  useLists: vi.fn(),
  useListItems: vi.fn(),
  useServiceSettings: vi.fn(),
  useRemoveItem: vi.fn(),
  useRemoveAvailable: vi.fn(),
  useSyncNow: vi.fn(),
  useTraktSettings: vi.fn(),
  useTraktLists: vi.fn(),
  useAddTraktList: vi.fn(),
  useRemoveTraktList: vi.fn(),
  useGeneralSettings: vi.fn(),
  useUpdateSyncInterval: vi.fn(),
  useUpdateAutoRemoveWhenAvailable: vi.fn(),
}))

import {
  useAddTraktList,
  useGeneralSettings,
  useListItems,
  useLists,
  useRemoveAvailable,
  useRemoveItem,
  useRemoveTraktList,
  useServiceSettings,
  useStatus,
  useSyncNow,
  useTraktLists,
  useTraktSettings,
  useUpdateAutoRemoveWhenAvailable,
  useUpdateSyncInterval,
} from "@/shared/lib/queries"
import { ListSyncarr } from "@/features/list-syncarr/ListSyncarr"
import { LIST_SYNCARR_TAB_STORAGE_KEY } from "@/features/list-syncarr/list-syncarr-tab"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import type {
  Item,
  ListSummary,
  ServicesSettings,
  Status,
  TraktSettings,
} from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"

/** Build a mutation-shaped stub; typed loosely as these are test doubles. */
function mutation(mutate: unknown, isPending = false) {
  return { mutate, isPending } as never
}

const TRAKT_SETTINGS: TraktSettings = {
  client_id: "abcd1234",
  client_id_hint: "1234",
  client_id_set: true,
  client_secret_set: true,
  connected: true,
  lists: [],
}

function render(ui: ReactElement) {
  return rtlRender(<TooltipProvider>{ui}</TooltipProvider>)
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(useStatus).mockReturnValue(queryResult<Status>(undefined, false))
  vi.mocked(useLists).mockReturnValue(queryResult<ListSummary[]>([], false))
  vi.mocked(useListItems).mockReturnValue(queryResult<Item[]>([], false))
  vi.mocked(useServiceSettings).mockReturnValue(
    queryResult<ServicesSettings>(undefined, false),
  )
  vi.mocked(useRemoveItem).mockReturnValue(mutation(vi.fn()))
  vi.mocked(useRemoveAvailable).mockReturnValue(mutation(vi.fn()))
  vi.mocked(useSyncNow).mockReturnValue(mutation(vi.fn()))
  vi.mocked(useTraktSettings).mockReturnValue(queryResult(TRAKT_SETTINGS))
  vi.mocked(useTraktLists).mockReturnValue(queryResult([], false))
  vi.mocked(useAddTraktList).mockReturnValue(mutation(vi.fn()))
  vi.mocked(useRemoveTraktList).mockReturnValue(mutation(vi.fn()))
  vi.mocked(useGeneralSettings).mockReturnValue(
    queryResult({
      interval_seconds: 60,
      sync_interval_minutes: 15,
      trending_sync_interval_minutes: 60,
      anime_ids_refresh_days: 3,
      auto_remove_when_available: false,
    }),
  )
  vi.mocked(useUpdateSyncInterval).mockReturnValue(mutation(vi.fn()))
  vi.mocked(useUpdateAutoRemoveWhenAvailable).mockReturnValue(mutation(vi.fn()))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("ListSyncarr", () => {
  it("renders the page header above the tabs", () => {
    render(<ListSyncarr />)
    expect(
      screen.getByRole("heading", { name: "List-Syncarr" }),
    ).toBeInTheDocument()
    expect(
      screen.getByText((text) =>
        text.includes("Mirror your Trakt lists to Seer"),
      ),
    ).toBeInTheDocument()
  })

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
      screen.getByText(
        "Choose which Trakt lists the engine keeps in sync, and how it polls and removes them.",
      ),
    ).toBeInTheDocument()
  })

  it("restores the Settings tab from localStorage", () => {
    localStorage.setItem(LIST_SYNCARR_TAB_STORAGE_KEY, "settings")
    render(<ListSyncarr />)
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(
      screen.getByText(
        "Choose which Trakt lists the engine keeps in sync, and how it polls and removes them.",
      ),
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
    await user.click(screen.getByRole("tab", { name: "Settings" }))
    expect(
      screen.getByText(
        "Choose which Trakt lists the engine keeps in sync, and how it polls and removes them.",
      ),
    ).toBeInTheDocument()
  })
})
