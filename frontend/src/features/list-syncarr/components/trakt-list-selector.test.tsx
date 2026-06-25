import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
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
import type { TraktListEntry, TraktSettings } from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"

/** Build a mutation-shaped stub; typed loosely as these are test doubles. */
function mutation(mutate: unknown, isPending = false) {
  return { mutate, isPending } as never
}

const SETTINGS: TraktSettings = {
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

  it("discovers lists and toggles their selection", async () => {
    const user = userEvent.setup()
    render(<TraktListSelector />)
    expect(screen.getByText("TV")).toBeInTheDocument()
    expect(screen.getByText("anime")).toBeInTheDocument() // null name -> slug
    expect(screen.getByText("(6 items)")).toBeInTheDocument()
    expect(screen.getByText("(0 items)")).toBeInTheDocument() // null count -> 0

    await user.click(screen.getByRole("switch", { name: "Sync tv" }))
    expect(addMutate).toHaveBeenCalledWith({ owner_user: "me", slug: "tv" })

    await user.click(screen.getByRole("switch", { name: "Sync anime" }))
    expect(removeMutate).toHaveBeenCalledWith({ owner_user: "me", slug: "anime" })
  })

  it("prompts to connect when Trakt is not connected", () => {
    vi.mocked(useTraktSettings).mockReturnValue(
      queryResult<TraktSettings>({ ...SETTINGS, connected: false }),
    )
    render(<TraktListSelector />)
    expect(
      screen.getByText("Connect Trakt to discover your lists."),
    ).toBeInTheDocument()
  })

  it("shows a loading state for discovered lists", () => {
    vi.mocked(useTraktLists).mockReturnValue(
      queryResult<TraktListEntry[]>(undefined, true),
    )
    render(<TraktListSelector />)
    expect(screen.getByText("Loading lists…")).toBeInTheDocument()
  })

  it("shows an empty message when no lists are discovered", () => {
    vi.mocked(useTraktLists).mockReturnValue(
      queryResult<TraktListEntry[]>(undefined, false),
    )
    render(<TraktListSelector />)
    expect(
      screen.getByText("No lists found on your account."),
    ).toBeInTheDocument()
  })

  it("disables controls while mutations are pending", () => {
    vi.mocked(useTraktLists).mockReturnValue(queryResult(DISCOVERED))
    vi.mocked(useAddTraktList).mockReturnValue(mutation(addMutate, true))
    vi.mocked(useRemoveTraktList).mockReturnValue(mutation(removeMutate, true))
    render(<TraktListSelector />)
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled()
    expect(screen.getByRole("switch", { name: "Sync tv" })).toBeDisabled()
  })
})
