import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useTraktSettings: vi.fn(),
  useTraktAuthStatus: vi.fn(),
  useUpdateTraktSettings: vi.fn(),
  useStartTraktAuth: vi.fn(),
  useTestTrakt: vi.fn(),
  useServiceSettings: vi.fn(),
  useUpdateServiceSettings: vi.fn(),
  useTestService: vi.fn(),
  useStatus: vi.fn(),
  useSetDryRun: vi.fn(),
  useGeneralSettings: vi.fn(),
  useUpdateStatusInterval: vi.fn(),
}))

const { setThemeMock } = vi.hoisted(() => ({ setThemeMock: vi.fn() }))
vi.mock("@/shared/components/theme-provider", () => ({
  useTheme: () => ({ theme: "dark", resolvedTheme: "dark", setTheme: setThemeMock }),
}))

import {
  useGeneralSettings,
  useServiceSettings,
  useSetDryRun,
  useStartTraktAuth,
  useStatus,
  useTestService,
  useTestTrakt,
  useTraktAuthStatus,
  useTraktSettings,
  useUpdateServiceSettings,
  useUpdateStatusInterval,
  useUpdateTraktSettings,
} from "@/shared/lib/queries"
import { Settings } from "@/features/settings/Settings"
import type {
  ServicesSettings,
  Status,
  TraktAuthStatus,
  TraktSettings,
  TraktTestResult,
} from "@/shared/lib/api"
import { SETTINGS_TAB_STORAGE_KEY } from "@/features/settings/settings-tab"
import { queryResult } from "@/shared/test/mock-query"

/** Build a mutation-shaped stub; typed loosely as these are test doubles. */
function mutation(mutate: unknown, isPending = false, data?: unknown) {
  return { mutate, isPending, data } as never
}

const SETTINGS: TraktSettings = {
  client_id_hint: "1234",
  client_id_set: true,
  client_secret_set: true,
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
  tmdb: { api_key_set: false },
  omdb: { api_key_set: false },
  sabnzbd: { url: "", api_key_set: false },
  qbittorrent: { url: "", api_key_set: false },
}

const STATUS: Status = {
  dry_run: true,
  trakt_connected: false,
  counts: { synced: 0, requested: 0, available: 0, removed: 0 },
}

let updateMutate: ReturnType<typeof vi.fn>
let startMutate: ReturnType<typeof vi.fn>
let testMutate: ReturnType<typeof vi.fn>
let serviceUpdateMutate: ReturnType<typeof vi.fn>
let serviceTestMutate: ReturnType<typeof vi.fn>
let setDryRunMutate: ReturnType<typeof vi.fn>
let updateStatusIntervalMutate: ReturnType<typeof vi.fn>

beforeEach(() => {
  localStorage.removeItem(SETTINGS_TAB_STORAGE_KEY)

  updateMutate = vi.fn()
  startMutate = vi.fn()
  testMutate = vi.fn()
  serviceUpdateMutate = vi.fn()
  serviceTestMutate = vi.fn()
  setDryRunMutate = vi.fn()
  updateStatusIntervalMutate = vi.fn()

  vi.mocked(useTraktSettings).mockReturnValue(queryResult(SETTINGS))
  vi.mocked(useTraktAuthStatus).mockReturnValue(queryResult(IDLE_AUTH))
  vi.mocked(useUpdateTraktSettings).mockReturnValue(mutation(updateMutate))
  vi.mocked(useStartTraktAuth).mockReturnValue(mutation(startMutate))
  vi.mocked(useTestTrakt).mockReturnValue(mutation(testMutate))
  vi.mocked(useServiceSettings).mockReturnValue(queryResult(SERVICES))
  vi.mocked(useUpdateServiceSettings).mockReturnValue(mutation(serviceUpdateMutate))
  vi.mocked(useTestService).mockReturnValue(mutation(serviceTestMutate))
  vi.mocked(useStatus).mockReturnValue(queryResult(STATUS))
  vi.mocked(useSetDryRun).mockReturnValue(mutation(setDryRunMutate))
  vi.mocked(useGeneralSettings).mockReturnValue(
    queryResult({ interval_seconds: 60 }),
  )
  vi.mocked(useUpdateStatusInterval).mockReturnValue(
    mutation(updateStatusIntervalMutate),
  )
})

afterEach(() => {
  // Some tests stub `localStorage`; restore it so the next `beforeEach` (which
  // reads it) is unaffected.
  vi.unstubAllGlobals()
})

function withTestResult(data: TraktTestResult) {
  vi.mocked(useTestTrakt).mockReturnValue(mutation(testMutate, false, data))
}

/** Render Settings and activate the Trakt tab (General is the default tab). */
async function renderTrakt() {
  const user = userEvent.setup()
  render(<Settings />)
  await user.click(screen.getByRole("tab", { name: "Trakt" }))
  return user
}

describe("Settings — credentials", () => {
  it("shows a loading state while the settings load", async () => {
    vi.mocked(useTraktSettings).mockReturnValue(
      queryResult<TraktSettings>(undefined, true),
    )
    await renderTrakt()
    expect(screen.getByText("Loading…")).toBeInTheDocument()
  })

  it("shows saved hints and the connected state", async () => {
    await renderTrakt()
    expect(screen.getByText("Saved (…1234)")).toBeInTheDocument()
    expect(screen.getByText("Saved")).toBeInTheDocument()
    expect(screen.getByText("Connected")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Re-connect Trakt" }),
    ).toBeInTheDocument()
  })

  it("shows 'Not set' hints and disconnected state without settings", async () => {
    vi.mocked(useTraktSettings).mockReturnValue(
      queryResult<TraktSettings>(undefined, false),
    )
    await renderTrakt()
    expect(screen.getAllByText("Not set")).toHaveLength(2)
    expect(screen.getByText("Not connected")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Connect Trakt" }),
    ).toBeInTheDocument()
  })

  it("saves only the fields that were entered", async () => {
    const user = await renderTrakt()
    await user.type(screen.getByPlaceholderText("Trakt client id"), "cid")
    await user.type(
      screen.getByPlaceholderText("Leave blank to keep current"),
      "sec",
    )
    await user.click(screen.getByRole("button", { name: "Save credentials" }))
    expect(updateMutate).toHaveBeenCalledWith({
      client_id: "cid",
      client_secret: "sec",
    })
  })

  it("saves an empty body when nothing was entered", async () => {
    const user = await renderTrakt()
    await user.click(screen.getByRole("button", { name: "Save credentials" }))
    expect(updateMutate).toHaveBeenCalledWith({})
  })
})

describe("Settings — connection", () => {
  it("starts auth and tests the connection", async () => {
    const user = await renderTrakt()
    await user.click(screen.getByRole("button", { name: "Re-connect Trakt" }))
    await user.click(screen.getByRole("button", { name: "Test connection" }))
    expect(startMutate).toHaveBeenCalledTimes(1)
    expect(testMutate).toHaveBeenCalledTimes(1)
  })

  it("shows the device code while authorisation is pending", async () => {
    vi.mocked(useTraktAuthStatus).mockReturnValue(
      queryResult<TraktAuthStatus>({
        state: "pending",
        user_code: "ABCD-1234",
        verification_url: "https://trakt.tv/activate",
        message: "Waiting for you",
        connected: false,
      }),
    )
    await renderTrakt()
    expect(screen.getByText("ABCD-1234")).toBeInTheDocument()
    expect(screen.getByText("Waiting for you")).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: "https://trakt.tv/activate" }),
    ).toHaveAttribute("href", "https://trakt.tv/activate")
  })

  it("falls back to the default activate URL when none is given", async () => {
    vi.mocked(useTraktAuthStatus).mockReturnValue(
      queryResult<TraktAuthStatus>({
        state: "pending",
        user_code: "ABCD-1234",
        verification_url: null,
        message: "Waiting",
        connected: false,
      }),
    )
    await renderTrakt()
    expect(
      screen.getByRole("link", { name: "trakt.tv/activate" }),
    ).toHaveAttribute("href", "https://trakt.tv/activate")
  })

  it("hides the code block when pending without a user code", async () => {
    vi.mocked(useTraktAuthStatus).mockReturnValue(
      queryResult<TraktAuthStatus>({
        state: "pending",
        user_code: null,
        verification_url: null,
        message: "Waiting",
        connected: false,
      }),
    )
    await renderTrakt()
    expect(screen.queryByText(/enter code/i)).not.toBeInTheDocument()
  })

  it("shows a failure message when authorisation failed", async () => {
    vi.mocked(useTraktAuthStatus).mockReturnValue(
      queryResult<TraktAuthStatus>({
        state: "failed",
        user_code: null,
        verification_url: null,
        message: "Authorisation did not complete",
        connected: false,
      }),
    )
    await renderTrakt()
    expect(
      screen.getByText("Authorisation did not complete"),
    ).toBeInTheDocument()
  })

  it("renders nothing extra when the auth status is unknown", async () => {
    vi.mocked(useTraktAuthStatus).mockReturnValue(
      queryResult<TraktAuthStatus>(undefined),
    )
    await renderTrakt()
    expect(screen.queryByText(/enter code/i)).not.toBeInTheDocument()
  })

  it("shows a successful test result with the signed-in user", async () => {
    withTestResult({ ok: true, user: "erena", message: "Connection OK" })
    await renderTrakt()
    expect(screen.getByText("Connection OK — erena")).toBeInTheDocument()
  })

  it("shows a successful test result without a user", async () => {
    withTestResult({ ok: true, user: null, message: "Connection OK" })
    await renderTrakt()
    expect(screen.getByText("Connection OK")).toBeInTheDocument()
  })

  it("shows a failed test result message", async () => {
    withTestResult({ ok: false, user: null, message: "no token" })
    await renderTrakt()
    expect(screen.getByText("no token")).toBeInTheDocument()
  })
})

describe("Settings — general", () => {
  it("is the default tab and shows dry-run on", () => {
    render(<Settings />)
    expect(screen.getByText("Dry-run mode")).toBeInTheDocument()
    expect(
      screen.getByRole("switch", { name: "Toggle dry-run mode" }),
    ).toBeChecked()
  })

  it("toggles dry-run mode", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("switch", { name: "Toggle dry-run mode" }))
    expect(setDryRunMutate).toHaveBeenCalledWith(false)
  })

  it("disables the dry-run switch while the status is pending", () => {
    vi.mocked(useSetDryRun).mockReturnValue(mutation(setDryRunMutate, true))
    render(<Settings />)
    expect(
      screen.getByRole("switch", { name: "Toggle dry-run mode" }),
    ).toBeDisabled()
  })

  it("disables the dry-run switch until the status loads", () => {
    vi.mocked(useStatus).mockReturnValue(queryResult<Status>(undefined))
    render(<Settings />)
    expect(
      screen.getByRole("switch", { name: "Toggle dry-run mode" }),
    ).toBeDisabled()
  })

  it("shows the configured status-check interval", () => {
    vi.mocked(useGeneralSettings).mockReturnValue(
      queryResult({ interval_seconds: 45 }),
    )
    render(<Settings />)
    expect(screen.getByText("Status check interval")).toBeInTheDocument()
    expect(screen.getByRole("combobox")).toHaveTextContent("45 seconds")
  })

  it("falls back to a 60s interval when general settings are unset", () => {
    vi.mocked(useGeneralSettings).mockReturnValue(queryResult(undefined))
    render(<Settings />)
    expect(screen.getByRole("combobox")).toHaveTextContent("60 seconds")
  })

  it("updates the status-check interval", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("combobox"))
    await user.click(screen.getByRole("option", { name: "30 seconds" }))
    expect(updateStatusIntervalMutate).toHaveBeenCalledWith({
      interval_seconds: 30,
    })
  })

  it("changes the colour theme", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("button", { name: "Light" }))
    expect(setThemeMock).toHaveBeenCalledWith("light")
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

  it("renders an API-key-only service (TMDB) with no URL field", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "TMDB" }))
    // An API-key-only service shows no URL row.
    expect(screen.queryByText("URL")).not.toBeInTheDocument()
    expect(screen.getByText("API key")).toBeInTheDocument()
    expect(screen.getByText("No key")).toBeInTheDocument()
  })

  it("saves only the API key for an API-key-only service", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "TMDB" }))
    await user.type(
      screen.getByPlaceholderText("Leave blank to keep current"),
      "tk",
    )
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(serviceUpdateMutate).toHaveBeenCalledWith({
      name: "tmdb",
      body: { api_key: "tk" },
    })
  })

  it("renders qBittorrent with url and api key and no stored secret", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "qBittorrent" }))
    expect(screen.getByText("URL")).toBeInTheDocument()
    expect(screen.getByText("API key")).toBeInTheDocument()
    expect(screen.getByText("No key")).toBeInTheDocument()
    // Both the URL and API key hints read "Not set" when unconfigured.
    expect(screen.getAllByText("Not set")).toHaveLength(2)
  })

  it("shows qBittorrent saved hints when already configured", async () => {
    vi.mocked(useServiceSettings).mockReturnValue(
      queryResult<ServicesSettings>({
        ...SERVICES,
        qbittorrent: {
          url: "http://qb:8080",
          api_key_set: true,
        },
      }),
    )
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "qBittorrent" }))
    expect(screen.getByText("Saved: http://qb:8080")).toBeInTheDocument()
    expect(screen.getByText("Key set")).toBeInTheDocument()
    // The API key hint reads the bare "Saved".
    expect(screen.getByText("Saved")).toBeInTheDocument()
  })

  it("falls back gracefully for qBittorrent when the query has no data", async () => {
    vi.mocked(useServiceSettings).mockReturnValue(
      queryResult<ServicesSettings>(undefined),
    )
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "qBittorrent" }))
    expect(screen.getByText("No key")).toBeInTheDocument()
    expect(screen.getByPlaceholderText("http://host:port")).toBeInTheDocument()
    expect(
      screen.getByPlaceholderText("Leave blank to keep current"),
    ).toBeInTheDocument()
  })

  it("saves the URL and API key for qBittorrent", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "qBittorrent" }))
    await user.type(
      screen.getByPlaceholderText("http://host:port"),
      "http://qb:8080",
    )
    await user.type(
      screen.getByPlaceholderText("Leave blank to keep current"),
      "qbt_key",
    )
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(serviceUpdateMutate).toHaveBeenCalledWith({
      name: "qbittorrent",
      body: { url: "http://qb:8080", api_key: "qbt_key" },
    })
  })

  it("saves an empty body for qBittorrent when nothing is entered", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "qBittorrent" }))
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(serviceUpdateMutate).toHaveBeenCalledWith({
      name: "qbittorrent",
      body: {},
    })
  })
})

describe("Settings — tab persistence", () => {
  it("restores the previously selected tab from localStorage", () => {
    localStorage.setItem(SETTINGS_TAB_STORAGE_KEY, "trakt")
    render(<Settings />)
    expect(screen.getByRole("tab", { name: "Trakt" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(screen.getByText("Trakt credentials")).toBeInTheDocument()
  })

  it("persists the selected tab and restores it on re-render", async () => {
    const user = userEvent.setup()
    const { unmount } = render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Sonarr" }))
    expect(localStorage.getItem(SETTINGS_TAB_STORAGE_KEY)).toBe("sonarr")

    unmount()
    render(<Settings />)
    expect(screen.getByRole("tab", { name: "Sonarr" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
  })

  it("falls back to the General tab when the stored value is invalid", () => {
    localStorage.setItem(SETTINGS_TAB_STORAGE_KEY, "not-a-tab")
    render(<Settings />)
    expect(screen.getByRole("tab", { name: "General" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
  })

  it("stays usable when localStorage is unavailable", async () => {
    vi.stubGlobal("localStorage", undefined)
    const user = userEvent.setup()
    render(<Settings />)
    // Defaults to the General tab without throwing.
    expect(screen.getByRole("tab", { name: "General" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    // Switching still works; the persistence write is safely skipped.
    await user.click(screen.getByRole("tab", { name: "Trakt" }))
    expect(screen.getByText("Trakt credentials")).toBeInTheDocument()
  })
})
