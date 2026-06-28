import { render as rtlRender, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
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
  useRemoveTraktList,
  useTraktLists,
  useTraktSettings,
  useUpdateAutoRemoveWhenAvailable,
  useUpdateSyncInterval,
} from "@/shared/lib/queries"
import { ListSettings } from "@/features/list-syncarr/tabs/ListSettings"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import type {
  GeneralSettings,
  TraktListEntry,
  TraktSettings,
} from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"
import { expectHelpTooltip } from "@/shared/test/tooltip"

/** Build a mutation-shaped stub; typed loosely as these are test doubles. */
function mutation(mutate: unknown, isPending = false) {
  return { mutate, isPending } as never
}

const SETTINGS: TraktSettings = {
  client_id: "abcd1234",
  client_id_hint: "1234",
  client_id_set: true,
  client_secret_set: true,
  connected: true,
  lists: [{ owner_user: "me", slug: "movies", name: "Movies" }],
}

const DISCOVERED: TraktListEntry[] = [
  { name: "TV", slug: "tv", owner_user: "me", item_count: 6, selected: false },
  { name: null, slug: "anime", owner_user: "me", item_count: null, selected: true },
]

const GENERAL: GeneralSettings = {
  interval_seconds: 60,
  sync_interval_minutes: 15,
  auto_remove_when_available: false,
}

function render(ui: ReactElement) {
  return rtlRender(<TooltipProvider>{ui}</TooltipProvider>)
}

let addMutate: ReturnType<typeof vi.fn>
let removeMutate: ReturnType<typeof vi.fn>
let syncIntervalMutate: ReturnType<typeof vi.fn>
let autoRemoveMutate: ReturnType<typeof vi.fn>

beforeEach(() => {
  addMutate = vi.fn()
  removeMutate = vi.fn()
  syncIntervalMutate = vi.fn()
  autoRemoveMutate = vi.fn()
  vi.mocked(useTraktSettings).mockReturnValue(queryResult(SETTINGS))
  vi.mocked(useTraktLists).mockReturnValue(queryResult<TraktListEntry[]>([]))
  vi.mocked(useAddTraktList).mockReturnValue(mutation(addMutate))
  vi.mocked(useRemoveTraktList).mockReturnValue(mutation(removeMutate))
  vi.mocked(useGeneralSettings).mockReturnValue(queryResult(GENERAL))
  vi.mocked(useUpdateSyncInterval).mockReturnValue(mutation(syncIntervalMutate))
  vi.mocked(useUpdateAutoRemoveWhenAvailable).mockReturnValue(
    mutation(autoRemoveMutate),
  )
})

describe("ListSettings", () => {
  it("lists the synced lists with their owner/slug", () => {
    render(<ListSettings />)
    expect(screen.getByText("Movies")).toBeInTheDocument()
    expect(screen.getByText("(me/movies)")).toBeInTheDocument()
  })

  it("removes a synced list", async () => {
    const user = userEvent.setup()
    render(<ListSettings />)
    await user.click(screen.getByRole("button", { name: "Remove" }))
    expect(removeMutate).toHaveBeenCalledWith({ owner_user: "me", slug: "movies" })
  })

  it("shows an empty message when nothing is synced", () => {
    vi.mocked(useTraktSettings).mockReturnValue(
      queryResult<TraktSettings>({ ...SETTINGS, lists: [] }),
    )
    render(<ListSettings />)
    expect(screen.getByText("No lists selected yet.")).toBeInTheDocument()
  })

  it("adds a list by URL", async () => {
    const user = userEvent.setup()
    render(<ListSettings />)
    const input = screen.getByPlaceholderText(
      "https://trakt.tv/users/me/lists/anime",
    )
    await user.type(input, "https://trakt.tv/users/me/lists/anime")
    await user.click(screen.getByRole("button", { name: "Add" }))
    expect(addMutate).toHaveBeenCalledWith({
      url: "https://trakt.tv/users/me/lists/anime",
    })
  })

  it("discovers lists and toggles their selection", async () => {
    vi.mocked(useTraktLists).mockReturnValue(queryResult(DISCOVERED))
    const user = userEvent.setup()
    render(<ListSettings />)
    await user.click(screen.getByRole("tab", { name: "Your Trakt lists" }))

    expect(screen.getByText("TV")).toBeInTheDocument()
    expect(screen.getByText("anime")).toBeInTheDocument() // null name -> slug
    expect(screen.getByText("(6 items)")).toBeInTheDocument()
    expect(screen.getByText("(0 items)")).toBeInTheDocument() // null count -> 0

    await user.click(screen.getByRole("switch", { name: "Sync tv" }))
    expect(addMutate).toHaveBeenCalledWith({ owner_user: "me", slug: "tv" })

    await user.click(screen.getByRole("switch", { name: "Sync anime" }))
    expect(removeMutate).toHaveBeenCalledWith({ owner_user: "me", slug: "anime" })
  })

  it("prompts to connect when Trakt is not connected", async () => {
    vi.mocked(useTraktSettings).mockReturnValue(
      queryResult<TraktSettings>({ ...SETTINGS, connected: false }),
    )
    const user = userEvent.setup()
    render(<ListSettings />)
    await user.click(screen.getByRole("tab", { name: "Your Trakt lists" }))
    expect(
      screen.getByText("Connect Trakt to discover your lists."),
    ).toBeInTheDocument()
  })

  it("renders the empty, disconnected state before settings load", async () => {
    // Settings is undefined until the first fetch resolves: treat it as not
    // connected with nothing synced rather than crashing on the missing data.
    vi.mocked(useTraktSettings).mockReturnValue(
      queryResult<TraktSettings>(undefined),
    )
    const user = userEvent.setup()
    render(<ListSettings />)
    expect(screen.getByText("No lists selected yet.")).toBeInTheDocument()
    await user.click(screen.getByRole("tab", { name: "Your Trakt lists" }))
    expect(
      screen.getByText("Connect Trakt to discover your lists."),
    ).toBeInTheDocument()
  })

  it("shows a loading state for discovered lists", async () => {
    vi.mocked(useTraktLists).mockReturnValue(
      queryResult<TraktListEntry[]>(undefined, true),
    )
    const user = userEvent.setup()
    render(<ListSettings />)
    await user.click(screen.getByRole("tab", { name: "Your Trakt lists" }))
    expect(screen.getByText("Loading lists…")).toBeInTheDocument()
  })

  it("shows an empty message when no lists are discovered", async () => {
    vi.mocked(useTraktLists).mockReturnValue(
      queryResult<TraktListEntry[]>(undefined, false),
    )
    const user = userEvent.setup()
    render(<ListSettings />)
    await user.click(screen.getByRole("tab", { name: "Your Trakt lists" }))
    expect(
      screen.getByText("No lists found on your account."),
    ).toBeInTheDocument()
  })

  it("disables controls while mutations are pending", async () => {
    vi.mocked(useTraktLists).mockReturnValue(queryResult(DISCOVERED))
    vi.mocked(useAddTraktList).mockReturnValue(mutation(addMutate, true))
    vi.mocked(useRemoveTraktList).mockReturnValue(mutation(removeMutate, true))
    const user = userEvent.setup()
    render(<ListSettings />)
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled()
    await user.click(screen.getByRole("tab", { name: "Your Trakt lists" }))
    expect(screen.getByRole("switch", { name: "Sync tv" })).toBeDisabled()
  })
})

describe("ListSettings — sync behaviour", () => {
  it("toggles remove-from-Trakt-when-available on", async () => {
    const user = userEvent.setup()
    render(<ListSettings />)
    const toggle = screen.getByRole("switch", {
      name: "Toggle remove from Trakt when available",
    })
    expect(toggle).not.toBeChecked() // GENERAL has it off
    await user.click(toggle)
    expect(autoRemoveMutate).toHaveBeenCalledWith(true)
  })

  it("reflects the configured auto-remove state", () => {
    vi.mocked(useGeneralSettings).mockReturnValue(
      queryResult({ ...GENERAL, auto_remove_when_available: true }),
    )
    render(<ListSettings />)
    expect(
      screen.getByRole("switch", {
        name: "Toggle remove from Trakt when available",
      }),
    ).toBeChecked()
  })

  it("shows and updates the sync interval", async () => {
    vi.mocked(useGeneralSettings).mockReturnValue(
      queryResult({ ...GENERAL, sync_interval_minutes: 45 }),
    )
    const user = userEvent.setup()
    render(<ListSettings />)
    const combobox = screen.getByRole("combobox", { name: "Sync interval" })
    expect(combobox).toHaveTextContent("45 minutes")
    await user.click(combobox)
    await user.click(screen.getByRole("option", { name: "30 minutes" }))
    expect(syncIntervalMutate).toHaveBeenCalledWith(30)
  })

  it("shows help for sync behaviour controls", async () => {
    const user = userEvent.setup()
    render(<ListSettings />)
    await expectHelpTooltip(
      user,
      "Explain Remove from Trakt when available",
      "Removes the list entry and the Seer request once Seer reports the item available or partially available. A merely-requested item is not removed; media files in Radarr/Sonarr are untouched.",
    )
  })

  it("falls back to defaults when general settings are unset", () => {
    vi.mocked(useGeneralSettings).mockReturnValue(
      queryResult<GeneralSettings>(undefined),
    )
    render(<ListSettings />)
    expect(
      screen.getByRole("switch", {
        name: "Toggle remove from Trakt when available",
      }),
    ).not.toBeChecked()
    expect(
      screen.getByRole("combobox", { name: "Sync interval" }),
    ).toHaveTextContent("15 minutes")
  })
})
