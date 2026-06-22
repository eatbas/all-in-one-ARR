import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/lib/queries", () => ({
  useTraktSettings: vi.fn(),
  useTraktAuthStatus: vi.fn(),
  useTraktLists: vi.fn(),
  useUpdateTraktSettings: vi.fn(),
  useStartTraktAuth: vi.fn(),
  useTestTrakt: vi.fn(),
  useAddTraktList: vi.fn(),
  useRemoveTraktList: vi.fn(),
  useServiceSettings: vi.fn(),
  useUpdateServiceSettings: vi.fn(),
  useTestService: vi.fn(),
}))

import {
  useAddTraktList,
  useRemoveTraktList,
  useServiceSettings,
  useStartTraktAuth,
  useTestService,
  useTestTrakt,
  useTraktAuthStatus,
  useTraktLists,
  useTraktSettings,
  useUpdateServiceSettings,
  useUpdateTraktSettings,
} from "@/lib/queries"
import { Settings } from "@/pages/Settings"
import type {
  ServicesSettings,
  TraktAuthStatus,
  TraktListEntry,
  TraktSettings,
  TraktTestResult,
} from "@/lib/api"
import { queryResult } from "@/test/mock-query"

/** Build a mutation-shaped stub; typed loosely as these are test doubles. */
function mutation(mutate: unknown, isPending = false, data?: unknown) {
  return { mutate, isPending, data } as never
}

const SETTINGS: TraktSettings = {
  client_id_hint: "1234",
  client_id_set: true,
  client_secret_set: true,
  user: "me",
  connected: true,
  lists: [{ owner_user: "me", slug: "movies", name: "Movies" }],
}

const IDLE_AUTH: TraktAuthStatus = {
  state: "idle",
  user_code: null,
  verification_url: null,
  message: null,
  connected: false,
}

const SERVICES: ServicesSettings = {
  jellyseerr: { url: "http://js:5055", api_key_set: true },
  sonarr: { url: "", api_key_set: false },
  radarr: { url: "", api_key_set: false },
}

let updateMutate: ReturnType<typeof vi.fn>
let startMutate: ReturnType<typeof vi.fn>
let testMutate: ReturnType<typeof vi.fn>
let addMutate: ReturnType<typeof vi.fn>
let removeMutate: ReturnType<typeof vi.fn>
let serviceUpdateMutate: ReturnType<typeof vi.fn>
let serviceTestMutate: ReturnType<typeof vi.fn>

beforeEach(() => {
  updateMutate = vi.fn()
  startMutate = vi.fn()
  testMutate = vi.fn()
  addMutate = vi.fn()
  removeMutate = vi.fn()
  serviceUpdateMutate = vi.fn()
  serviceTestMutate = vi.fn()

  vi.mocked(useTraktSettings).mockReturnValue(queryResult(SETTINGS))
  vi.mocked(useTraktAuthStatus).mockReturnValue(queryResult(IDLE_AUTH))
  vi.mocked(useTraktLists).mockReturnValue(queryResult<TraktListEntry[]>([]))
  vi.mocked(useUpdateTraktSettings).mockReturnValue(mutation(updateMutate))
  vi.mocked(useStartTraktAuth).mockReturnValue(mutation(startMutate))
  vi.mocked(useTestTrakt).mockReturnValue(mutation(testMutate))
  vi.mocked(useAddTraktList).mockReturnValue(mutation(addMutate))
  vi.mocked(useRemoveTraktList).mockReturnValue(mutation(removeMutate))
  vi.mocked(useServiceSettings).mockReturnValue(queryResult(SERVICES))
  vi.mocked(useUpdateServiceSettings).mockReturnValue(mutation(serviceUpdateMutate))
  vi.mocked(useTestService).mockReturnValue(mutation(serviceTestMutate))
})

function withTestResult(data: TraktTestResult) {
  vi.mocked(useTestTrakt).mockReturnValue(mutation(testMutate, false, data))
}

describe("Settings — credentials", () => {
  it("shows a loading state while the settings load", () => {
    vi.mocked(useTraktSettings).mockReturnValue(
      queryResult<TraktSettings>(undefined, true),
    )
    render(<Settings />)
    expect(screen.getByText("Loading…")).toBeInTheDocument()
  })

  it("shows saved hints and the connected state", () => {
    render(<Settings />)
    expect(screen.getByText("Saved (…1234)")).toBeInTheDocument()
    expect(screen.getByText("Saved")).toBeInTheDocument()
    expect(screen.getByText("Connected")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Re-connect Trakt" }),
    ).toBeInTheDocument()
    // The synced list is listed with its owner/slug.
    expect(screen.getByText("Movies")).toBeInTheDocument()
    expect(screen.getByText("(me/movies)")).toBeInTheDocument()
  })

  it("shows 'Not set' hints and disconnected state without settings", () => {
    vi.mocked(useTraktSettings).mockReturnValue(
      queryResult<TraktSettings>(undefined, false),
    )
    render(<Settings />)
    expect(screen.getAllByText("Not set")).toHaveLength(2)
    expect(screen.getByText("Not connected")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Connect Trakt" }),
    ).toBeInTheDocument()
    expect(screen.getByText("No lists selected yet.")).toBeInTheDocument()
    expect(
      screen.getByText("Connect Trakt to discover your lists."),
    ).toBeInTheDocument()
  })

  it("saves only the fields that were entered", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.type(screen.getByPlaceholderText("Trakt client id"), "cid")
    await user.type(
      screen.getByPlaceholderText("Leave blank to keep current"),
      "sec",
    )
    await user.type(screen.getByPlaceholderText("me"), "bob")
    await user.click(screen.getByRole("button", { name: "Save credentials" }))
    expect(updateMutate).toHaveBeenCalledWith({
      client_id: "cid",
      client_secret: "sec",
      user: "bob",
    })
  })

  it("saves an empty body when nothing was entered", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("button", { name: "Save credentials" }))
    expect(updateMutate).toHaveBeenCalledWith({})
  })
})

describe("Settings — connection", () => {
  it("starts auth and tests the connection", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("button", { name: "Re-connect Trakt" }))
    await user.click(screen.getByRole("button", { name: "Test connection" }))
    expect(startMutate).toHaveBeenCalledTimes(1)
    expect(testMutate).toHaveBeenCalledTimes(1)
  })

  it("shows the device code while authorisation is pending", () => {
    vi.mocked(useTraktAuthStatus).mockReturnValue(
      queryResult<TraktAuthStatus>({
        state: "pending",
        user_code: "ABCD-1234",
        verification_url: "https://trakt.tv/activate",
        message: "Waiting for you",
        connected: false,
      }),
    )
    render(<Settings />)
    expect(screen.getByText("ABCD-1234")).toBeInTheDocument()
    expect(screen.getByText("Waiting for you")).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: "https://trakt.tv/activate" }),
    ).toHaveAttribute("href", "https://trakt.tv/activate")
  })

  it("falls back to the default activate URL when none is given", () => {
    vi.mocked(useTraktAuthStatus).mockReturnValue(
      queryResult<TraktAuthStatus>({
        state: "pending",
        user_code: "ABCD-1234",
        verification_url: null,
        message: "Waiting",
        connected: false,
      }),
    )
    render(<Settings />)
    expect(
      screen.getByRole("link", { name: "trakt.tv/activate" }),
    ).toHaveAttribute("href", "https://trakt.tv/activate")
  })

  it("hides the code block when pending without a user code", () => {
    vi.mocked(useTraktAuthStatus).mockReturnValue(
      queryResult<TraktAuthStatus>({
        state: "pending",
        user_code: null,
        verification_url: null,
        message: "Waiting",
        connected: false,
      }),
    )
    render(<Settings />)
    expect(screen.queryByText(/enter code/i)).not.toBeInTheDocument()
  })

  it("shows a failure message when authorisation failed", () => {
    vi.mocked(useTraktAuthStatus).mockReturnValue(
      queryResult<TraktAuthStatus>({
        state: "failed",
        user_code: null,
        verification_url: null,
        message: "Authorisation did not complete",
        connected: false,
      }),
    )
    render(<Settings />)
    expect(
      screen.getByText("Authorisation did not complete"),
    ).toBeInTheDocument()
  })

  it("renders nothing extra when the auth status is unknown", () => {
    vi.mocked(useTraktAuthStatus).mockReturnValue(
      queryResult<TraktAuthStatus>(undefined),
    )
    render(<Settings />)
    expect(screen.queryByText(/enter code/i)).not.toBeInTheDocument()
  })

  it("shows a successful test result with the signed-in user", () => {
    withTestResult({ ok: true, user: "erena", message: "Connection OK" })
    render(<Settings />)
    expect(screen.getByText("Connection OK — erena")).toBeInTheDocument()
  })

  it("shows a successful test result without a user", () => {
    withTestResult({ ok: true, user: null, message: "Connection OK" })
    render(<Settings />)
    expect(screen.getByText("Connection OK")).toBeInTheDocument()
  })

  it("shows a failed test result message", () => {
    withTestResult({ ok: false, user: null, message: "no token" })
    render(<Settings />)
    expect(screen.getByText("no token")).toBeInTheDocument()
  })
})

describe("Settings — lists", () => {
  const DISCOVERED: TraktListEntry[] = [
    { name: "TV", slug: "tv", owner_user: "me", item_count: 6, selected: false },
    { name: null, slug: "anime", owner_user: "me", item_count: null, selected: true },
  ]

  it("removes a synced list", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("button", { name: "Remove" }))
    expect(removeMutate).toHaveBeenCalledWith({ owner_user: "me", slug: "movies" })
  })

  it("adds a list by URL", async () => {
    const user = userEvent.setup()
    render(<Settings />)
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
    vi.mocked(useTraktLists).mockReturnValue(queryResult(DISCOVERED))
    render(<Settings />)
    expect(screen.getByText("TV")).toBeInTheDocument()
    expect(screen.getByText("anime")).toBeInTheDocument() // null name -> slug
    expect(screen.getByText("(6 items)")).toBeInTheDocument()
    expect(screen.getByText("(0 items)")).toBeInTheDocument() // null count -> 0

    await user.click(screen.getByRole("switch", { name: "Sync tv" }))
    expect(addMutate).toHaveBeenCalledWith({ owner_user: "me", slug: "tv" })

    await user.click(screen.getByRole("switch", { name: "Sync anime" }))
    expect(removeMutate).toHaveBeenCalledWith({ owner_user: "me", slug: "anime" })
  })

  it("shows a loading state for discovered lists", () => {
    vi.mocked(useTraktLists).mockReturnValue(
      queryResult<TraktListEntry[]>(undefined, true),
    )
    render(<Settings />)
    expect(screen.getByText("Loading lists…")).toBeInTheDocument()
  })

  it("shows an empty message when no lists are discovered", () => {
    vi.mocked(useTraktLists).mockReturnValue(
      queryResult<TraktListEntry[]>(undefined, false),
    )
    render(<Settings />)
    expect(
      screen.getByText("No lists found on your account."),
    ).toBeInTheDocument()
  })

  it("disables controls while mutations are pending", () => {
    vi.mocked(useTraktLists).mockReturnValue(queryResult(DISCOVERED))
    vi.mocked(useAddTraktList).mockReturnValue(mutation(addMutate, true))
    vi.mocked(useRemoveTraktList).mockReturnValue(mutation(removeMutate, true))
    render(<Settings />)
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled()
    expect(screen.getByRole("switch", { name: "Sync tv" })).toBeDisabled()
  })
})

describe("Settings — service tabs", () => {
  it("shows a service with a saved URL and key", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Jellyseerr" }))
    expect(screen.getByText("Saved: http://js:5055")).toBeInTheDocument()
    expect(screen.getByText("Key set")).toBeInTheDocument()
  })

  it("shows a service without a key as not set", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Sonarr" }))
    expect(screen.getByText("No key")).toBeInTheDocument()
    expect(screen.getAllByText("Not set").length).toBeGreaterThan(0)
  })

  it("falls back gracefully when the services query has no data", async () => {
    vi.mocked(useServiceSettings).mockReturnValue(
      queryResult<ServicesSettings>(undefined),
    )
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Radarr" }))
    expect(screen.getByText("No key")).toBeInTheDocument()
    expect(
      screen.getByPlaceholderText("http://host:port"),
    ).toBeInTheDocument()
  })

  it("saves a service URL and key", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Radarr" }))
    await user.type(
      screen.getByPlaceholderText("http://host:port"),
      "http://radarr:7878",
    )
    await user.type(
      screen.getByPlaceholderText("Leave blank to keep current"),
      "rk",
    )
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(serviceUpdateMutate).toHaveBeenCalledWith({
      name: "radarr",
      body: { url: "http://radarr:7878", api_key: "rk" },
    })
  })

  it("saves an empty body when nothing is entered", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Sonarr" }))
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(serviceUpdateMutate).toHaveBeenCalledWith({ name: "sonarr", body: {} })
  })

  it("tests a service connection", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Jellyseerr" }))
    await user.click(screen.getByRole("button", { name: "Test connection" }))
    expect(serviceTestMutate).toHaveBeenCalledWith("jellyseerr")
  })

  it("shows a successful test result", async () => {
    vi.mocked(useTestService).mockReturnValue(
      mutation(serviceTestMutate, false, {
        ok: true,
        detail: "Connected to Sonarr 4.0",
      }),
    )
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Sonarr" }))
    expect(screen.getByText("Connected to Sonarr 4.0")).toBeInTheDocument()
  })

  it("shows a failed test result", async () => {
    vi.mocked(useTestService).mockReturnValue(
      mutation(serviceTestMutate, false, {
        ok: false,
        detail: "Radarr returned HTTP 401",
      }),
    )
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Radarr" }))
    expect(screen.getByText("Radarr returned HTTP 401")).toBeInTheDocument()
  })
})
