import { render as rtlRender, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useTraktSettings: vi.fn(),
  useTraktLists: vi.fn(),
  useAddTraktList: vi.fn(),
  useRemoveTraktList: vi.fn(),
}))

import {
  useAddTraktList,
  useRemoveTraktList,
  useTraktLists,
  useTraktSettings,
} from "@/shared/lib/queries"
import { TraktListSelector } from "@/features/list-syncarr/components/trakt-list-selector"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import type { TraktListEntry, TraktSettings } from "@/shared/lib/api"
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

function render(ui: ReactElement) {
  return rtlRender(<TooltipProvider>{ui}</TooltipProvider>)
}

let addMutate: ReturnType<typeof vi.fn>
let removeMutate: ReturnType<typeof vi.fn>

beforeEach(() => {
  addMutate = vi.fn()
  removeMutate = vi.fn()
  vi.mocked(useTraktSettings).mockReturnValue(queryResult(SETTINGS))
  vi.mocked(useTraktLists).mockReturnValue(queryResult<TraktListEntry[]>(DISCOVERED))
  vi.mocked(useAddTraktList).mockReturnValue(mutation(addMutate))
  vi.mocked(useRemoveTraktList).mockReturnValue(mutation(removeMutate))
})

describe("TraktListSelector", () => {
  it("lists the synced lists with their owner/slug", () => {
    render(<TraktListSelector />)
    expect(screen.getByText("Movies")).toBeInTheDocument()
    expect(screen.getByText("(me/movies)")).toBeInTheDocument()
  })

  it("removes a synced list", async () => {
    const user = userEvent.setup()
    render(<TraktListSelector />)
    await user.click(screen.getByRole("button", { name: "Remove" }))
    expect(removeMutate).toHaveBeenCalledWith({ owner_user: "me", slug: "movies" })
  })

  it("shows an empty message when nothing is synced", () => {
    vi.mocked(useTraktSettings).mockReturnValue(
      queryResult<TraktSettings>({ ...SETTINGS, lists: [] }),
    )
    render(<TraktListSelector />)
    expect(screen.getByText("No lists selected yet.")).toBeInTheDocument()
  })

  it("adds a list by URL", async () => {
    const user = userEvent.setup()
    render(<TraktListSelector />)
    const input = screen.getByPlaceholderText(
      "https://trakt.tv/users/me/lists/anime",
    )
    await user.type(input, "https://trakt.tv/users/me/lists/anime")
    await user.click(screen.getByRole("button", { name: "Add" }))
    expect(addMutate).toHaveBeenCalledWith({
      url: "https://trakt.tv/users/me/lists/anime",
    })
  })

  it("shows help for adding a Trakt list by URL", async () => {
    const user = userEvent.setup()
    render(<TraktListSelector />)
    await expectHelpTooltip(
      user,
      "Explain Add by Trakt URL",
      "Adds a Trakt list by URL when it belongs to the connected account.",
    )
  })

  it("renders Syncing and Your Trakt lists tabs with Syncing selected by default", () => {
    render(<TraktListSelector />)
    expect(screen.getByRole("tab", { name: "Syncing" })).toBeInTheDocument()
    expect(
      screen.getByRole("tab", { name: "Your Trakt lists" }),
    ).toBeInTheDocument()
    expect(screen.getByText("Movies")).toBeInTheDocument()
  })

  it("discovers lists and toggles their selection", async () => {
    const user = userEvent.setup()
    render(<TraktListSelector />)
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

  it("shows help for discovered list switches", async () => {
    const user = userEvent.setup()
    render(<TraktListSelector />)
    await user.click(screen.getByRole("tab", { name: "Your Trakt lists" }))
    await expectHelpTooltip(
      user,
      "Explain Sync tv",
      "Turns syncing on or off for this discovered Trakt list.",
    )
  })

  it("prompts to connect when Trakt is not connected", async () => {
    vi.mocked(useTraktSettings).mockReturnValue(
      queryResult<TraktSettings>({ ...SETTINGS, connected: false }),
    )
    const user = userEvent.setup()
    render(<TraktListSelector />)
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
    render(<TraktListSelector />)
    await user.click(screen.getByRole("tab", { name: "Your Trakt lists" }))
    expect(screen.getByText("Loading lists…")).toBeInTheDocument()
  })

  it("shows an empty message when no lists are discovered", async () => {
    vi.mocked(useTraktLists).mockReturnValue(
      queryResult<TraktListEntry[]>(undefined, false),
    )
    const user = userEvent.setup()
    render(<TraktListSelector />)
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
    render(<TraktListSelector />)
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled()
    await user.click(screen.getByRole("tab", { name: "Your Trakt lists" }))
    expect(screen.getByRole("switch", { name: "Sync tv" })).toBeDisabled()
  })
})
