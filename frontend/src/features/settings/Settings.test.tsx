import { render as rtlRender, screen, fireEvent, act } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactElement } from "react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  queryKeys: {
    traktSettings: ["trakt", "settings"],
    traktLists: ["trakt", "lists"],
    database: ["database", "stats"],
    activity: ["activity"],
    lists: ["lists"],
    status: ["status"],
  },
  useTraktSettings: vi.fn(),
  useTraktAuthStatus: vi.fn(),
  useUpdateTraktSettings: vi.fn(),
  useStartTraktAuth: vi.fn(),
  useTestTrakt: vi.fn(),
  useServiceSettings: vi.fn(),
  useServiceStatuses: vi.fn(),
  useUpdateServiceSettings: vi.fn(),
  useTestService: vi.fn(),
  useGeneralSettings: vi.fn(),
  useUpdateStatusInterval: vi.fn(),
  useDatabaseStats: vi.fn(),
  useClearActivity: vi.fn(),
  useClearItems: vi.fn(),
  useClearPosters: vi.fn(),
}))

const { setThemeMock } = vi.hoisted(() => ({ setThemeMock: vi.fn() }))
vi.mock("@/shared/components/theme-context", () => ({
  useTheme: () => ({ theme: "dark", resolvedTheme: "dark", setTheme: setThemeMock }),
}))

import {
  useClearActivity,
  useClearItems,
  useClearPosters,
  useDatabaseStats,
  useGeneralSettings,
  useServiceSettings,
  useServiceStatuses,
  useStartTraktAuth,
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
  GeneralSettings,
  ServicesSettings,
  ServicesStatusResponse,
  TraktAuthStatus,
  TraktSettings,
  TraktTestResult,
} from "@/shared/lib/api"
import { SETTINGS_TAB_STORAGE_KEY } from "@/features/settings/settings-tab"
import { queryResult } from "@/shared/test/mock-query"

/** Render wrapped in a fresh TanStack Query client so `useQueryClient` works. */
function render(ui: ReactElement, options?: Parameters<typeof rtlRender>[1]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    queryClient,
    ...rtlRender(ui, {
      wrapper: ({ children }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      ),
      ...options,
    }),
  }
}

/** Build a mutation-shaped stub; typed loosely as these are test doubles. */
function mutation(
  mutateImpl: unknown,
  isPending = false,
  data?: unknown,
  callOnSuccess?: boolean,
) {
  const shouldCallOnSuccess = callOnSuccess ?? !isPending
  const mutate = vi.fn((vars: unknown, options?: { onSuccess?: () => void }) => {
    ;(mutateImpl as (vars: unknown) => void)(vars)
    // When simulating a pending mutation, the success callback has not fired
    // yet, so do not invoke it automatically. Tests can also suppress
    // onSuccess for settled-error scenarios.
    if (shouldCallOnSuccess && options?.onSuccess) {
      options.onSuccess()
    }
  })
  return { mutate, isPending, data } as never
}

const SETTINGS: TraktSettings = {
  client_id: "abcd1234",
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
  seer: { url: "http://js:5055", api_key_set: true },
  sonarr: { url: "", api_key_set: false },
  radarr: { url: "", api_key_set: false },
  tmdb: { api_key_set: false },
  omdb: { api_key_set: false },
  sabnzbd: { url: "", api_key_set: false },
  qbittorrent: { url: "", api_key_set: false },
}

let updateMutate: ReturnType<typeof vi.fn>
let startMutate: ReturnType<typeof vi.fn>
let testMutate: ReturnType<typeof vi.fn>
let serviceUpdateMutate: ReturnType<typeof vi.fn>
let serviceTestMutate: ReturnType<typeof vi.fn>
let updateStatusIntervalMutate: ReturnType<typeof vi.fn>
let clearActivityMutate: ReturnType<typeof vi.fn>
let clearItemsMutate: ReturnType<typeof vi.fn>
let clearPostersMutate: ReturnType<typeof vi.fn>

const DATABASE_STATS = {
  db_size_bytes: 1024,
  poster_cache_bytes: 2048,
  item_count: 5,
  activity_count: 12,
  list_state_count: 2,
}

beforeEach(() => {
  localStorage.removeItem(SETTINGS_TAB_STORAGE_KEY)

  updateMutate = vi.fn()
  startMutate = vi.fn()
  testMutate = vi.fn()
  serviceUpdateMutate = vi.fn()
  serviceTestMutate = vi.fn()
  updateStatusIntervalMutate = vi.fn()
  clearActivityMutate = vi.fn()
  clearItemsMutate = vi.fn()
  clearPostersMutate = vi.fn()

  vi.mocked(useTraktSettings).mockReturnValue(queryResult(SETTINGS))
  vi.mocked(useTraktAuthStatus).mockReturnValue(queryResult(IDLE_AUTH))
  vi.mocked(useUpdateTraktSettings).mockReturnValue(mutation(updateMutate))
  vi.mocked(useStartTraktAuth).mockReturnValue(mutation(startMutate))
  vi.mocked(useTestTrakt).mockReturnValue(mutation(testMutate))
  vi.mocked(useServiceSettings).mockReturnValue(queryResult(SERVICES))
  vi.mocked(useServiceStatuses).mockReturnValue(
    queryResult<ServicesStatusResponse>({
      interval_seconds: 60,
      last_check_at: null,
      services: {},
    }),
  )
  vi.mocked(useUpdateServiceSettings).mockReturnValue(mutation(serviceUpdateMutate))
  vi.mocked(useTestService).mockReturnValue(mutation(serviceTestMutate))
  vi.mocked(useGeneralSettings).mockReturnValue(
    queryResult({
      interval_seconds: 60,
      sync_interval_minutes: 15,
      auto_remove_when_available: false,
    }),
  )
  vi.mocked(useUpdateStatusInterval).mockReturnValue(
    mutation(updateStatusIntervalMutate),
  )
  vi.mocked(useDatabaseStats).mockReturnValue(queryResult(DATABASE_STATS))
  vi.mocked(useClearActivity).mockReturnValue(mutation(clearActivityMutate))
  vi.mocked(useClearItems).mockReturnValue(mutation(clearItemsMutate))
  vi.mocked(useClearPosters).mockReturnValue(mutation(clearPostersMutate))
})

afterEach(() => {
  // Some tests stub `localStorage`; restore it so the next `beforeEach` (which
  // reads it) is unaffected.
  vi.unstubAllGlobals()
  // Ensure fake timers never leak between tests.
  vi.useRealTimers()
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

/** Render Settings and activate the Database tab. */
async function renderDatabase() {
  const user = userEvent.setup()
  render(<Settings />)
  await user.click(screen.getByRole("tab", { name: "Database" }))
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
    expect(screen.getAllByText("Saved").length).toBeGreaterThan(0)
    expect(screen.getByText("Connected")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Re-connect Trakt" }),
    ).toBeInTheDocument()
  })

  it("does not render the list-management selector on the Trakt tab", async () => {
    await renderTrakt()
    expect(screen.getByText("Trakt credentials")).toBeInTheDocument()
    expect(
      screen.queryByRole("tab", { name: "Your Trakt lists" }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText("Add by Trakt URL")).not.toBeInTheDocument()
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

  it("hydrates the saved client id and leaves the secret input blank", async () => {
    await renderTrakt()
    expect(screen.getByPlaceholderText("Trakt client id")).toHaveValue(
      SETTINGS.client_id,
    )
    expect(screen.getByPlaceholderText("Leave blank to keep current")).toHaveValue(
      "",
    )
  })

  it("shows a saving hint while the update is pending", async () => {
    const { rerender } = render(<Settings />)
    await userEvent.click(screen.getByRole("tab", { name: "Trakt" }))
    vi.mocked(useUpdateTraktSettings).mockReturnValue(
      mutation(updateMutate, true),
    )
    rerender(<Settings />)
    expect(screen.getByText("Saving…")).toBeInTheDocument()
  })

  it("does not autosave on initial render", async () => {
    await renderTrakt()
    expect(updateMutate).not.toHaveBeenCalled()
  })

  it("autosaves only the fields that changed after debounce", async () => {
    await renderTrakt()
    vi.useFakeTimers()

    act(() => {
      fireEvent.change(screen.getByPlaceholderText("Trakt client id"), {
        target: { value: `${SETTINGS.client_id}cid` },
      })
      fireEvent.change(
        screen.getByPlaceholderText("Leave blank to keep current"),
        { target: { value: "sec" } },
      )
    })
    expect(updateMutate).not.toHaveBeenCalled()

    act(() => vi.advanceTimersByTime(800))
    expect(updateMutate).toHaveBeenCalledTimes(1)
    expect(updateMutate).toHaveBeenCalledWith({
      client_id: `${SETTINGS.client_id}cid`,
      client_secret: "sec",
    })

    vi.useRealTimers()
  })

  it("autosaves only a secret edit without resending the unchanged client id", async () => {
    await renderTrakt()
    vi.useFakeTimers()

    act(() =>
      fireEvent.change(
        screen.getByPlaceholderText("Leave blank to keep current"),
        { target: { value: "sec" } },
      ),
    )
    act(() => vi.advanceTimersByTime(800))
    expect(updateMutate).toHaveBeenCalledWith({ client_secret: "sec" })

    vi.useRealTimers()
  })

  it("clears the secret input after a successful autosave", async () => {
    await renderTrakt()
    vi.useFakeTimers()

    const secretInput = screen.getByPlaceholderText("Leave blank to keep current")
    act(() => fireEvent.change(secretInput, { target: { value: "sec" } }))
    act(() => vi.advanceTimersByTime(800))
    expect(secretInput).toHaveValue("")

    vi.useRealTimers()
  })

  it("does not send duplicate Trakt saves while a save is pending", async () => {
    const { rerender } = render(<Settings />)
    await userEvent.click(screen.getByRole("tab", { name: "Trakt" }))
    vi.useFakeTimers()

    act(() =>
      fireEvent.change(screen.getByPlaceholderText("Trakt client id"), {
        target: { value: `${SETTINGS.client_id}cid` },
      }),
    )
    act(() => vi.advanceTimersByTime(800))
    expect(updateMutate).toHaveBeenCalledTimes(1)

    // Simulate the mutation entering the pending state (save in-flight) and a
    // re-render with a fresh mutation result object. The original effect
    // depended on the whole result object, which would schedule another save;
    // the fixed effect depends on the stable mutate function and the isPending
    // guard.
    vi.mocked(useUpdateTraktSettings).mockReturnValue(
      mutation(updateMutate, true),
    )
    rerender(<Settings />)

    act(() => vi.advanceTimersByTime(800))
    expect(updateMutate).toHaveBeenCalledTimes(1)

    vi.useRealTimers()
  })

  it("does not retry a failed Trakt save until a further edit", async () => {
    // Suppress onSuccess so the dirty draft survives the first submission,
    // simulating a failed save that settles back to non-pending.
    vi.mocked(useUpdateTraktSettings).mockReturnValue(
      mutation(updateMutate, false, undefined, false),
    )
    const { rerender } = render(<Settings />)
    await userEvent.click(screen.getByRole("tab", { name: "Trakt" }))
    vi.useFakeTimers()

    act(() =>
      fireEvent.change(screen.getByPlaceholderText("Trakt client id"), {
        target: { value: `${SETTINGS.client_id}cid` },
      }),
    )
    act(() =>
      fireEvent.change(
        screen.getByPlaceholderText("Leave blank to keep current"),
        { target: { value: "secret-before-failure" } },
      ),
    )
    act(() => vi.advanceTimersByTime(800))
    expect(updateMutate).toHaveBeenCalledTimes(1)
    expect(updateMutate).toHaveBeenLastCalledWith({
      client_id: `${SETTINGS.client_id}cid`,
      client_secret: "secret-before-failure",
    })

    // Mutation enters pending state.
    vi.mocked(useUpdateTraktSettings).mockReturnValue(
      mutation(updateMutate, true),
    )
    rerender(<Settings />)

    act(() => vi.advanceTimersByTime(800))
    expect(updateMutate).toHaveBeenCalledTimes(1)

    // Mutation fails/settles back to non-pending without calling onSuccess;
    // the dirty body must not be re-submitted automatically.
    vi.mocked(useUpdateTraktSettings).mockReturnValue(
      mutation(updateMutate, false, undefined, false),
    )
    rerender(<Settings />)

    act(() => vi.advanceTimersByTime(800))
    expect(updateMutate).toHaveBeenCalledTimes(1)

    act(() =>
      fireEvent.change(
        screen.getByPlaceholderText("Leave blank to keep current"),
        { target: { value: "secret-after-failure" } },
      ),
    )
    act(() => vi.advanceTimersByTime(800))
    expect(updateMutate).toHaveBeenCalledTimes(2)
    expect(updateMutate).toHaveBeenLastCalledWith({
      client_id: `${SETTINGS.client_id}cid`,
      client_secret: "secret-after-failure",
    })

    vi.useRealTimers()
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

  it("invalidates Trakt settings and lists when auth becomes connected", async () => {
    const { queryClient, rerender } = render(<Settings />)
    const user = userEvent.setup()
    await user.click(screen.getByRole("tab", { name: "Trakt" }))

    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    vi.mocked(useTraktAuthStatus).mockReturnValue(
      queryResult<TraktAuthStatus>({
        state: "success",
        user_code: null,
        verification_url: null,
        message: null,
        connected: true,
      }),
    )

    // Re-render so the newly connected auth status reaches the effect.
    rerender(<Settings />)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["trakt", "settings"] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["trakt", "lists"] })
  })

  it("only invalidates once when auth stays connected", async () => {
    const { queryClient, rerender } = render(<Settings />)
    const user = userEvent.setup()
    await user.click(screen.getByRole("tab", { name: "Trakt" }))

    const connectedAuth: TraktAuthStatus = {
      state: "success",
      user_code: null,
      verification_url: null,
      message: null,
      connected: true,
    }
    vi.mocked(useTraktAuthStatus).mockReturnValue(
      queryResult<TraktAuthStatus>(connectedAuth),
    )
    rerender(<Settings />)

    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    // Re-rendering with a fresh connected auth object should not invalidate again
    // because the ref already recorded the connected state.
    vi.mocked(useTraktAuthStatus).mockReturnValue(
      queryResult<TraktAuthStatus>({ ...connectedAuth }),
    )
    rerender(<Settings />)
    expect(invalidate).not.toHaveBeenCalled()
  })
})

describe("Settings — general", () => {
  it("shows the configured status-check interval", () => {
    vi.mocked(useGeneralSettings).mockReturnValue(
      queryResult({
        interval_seconds: 45,
        sync_interval_minutes: 15,
        auto_remove_when_available: false,
      }),
    )
    render(<Settings />)
    expect(screen.getByText("Status check interval")).toBeInTheDocument()
    expect(
      screen.getByRole("combobox", { name: "Status check interval" }),
    ).toHaveTextContent("45 seconds")
  })

  it("falls back to the default status interval when general settings are unset", () => {
    vi.mocked(useGeneralSettings).mockReturnValue(
      queryResult<GeneralSettings>(undefined),
    )
    render(<Settings />)
    expect(
      screen.getByRole("combobox", { name: "Status check interval" }),
    ).toHaveTextContent("60 seconds")
  })

  it("updates the status-check interval", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(
      screen.getByRole("combobox", { name: "Status check interval" }),
    )
    await user.click(screen.getByRole("option", { name: "30 seconds" }))
    expect(updateStatusIntervalMutate).toHaveBeenCalledWith({
      interval_seconds: 30,
    })
  })

  it("no longer renders the sync interval (moved to List-Syncarr settings)", () => {
    render(<Settings />)
    expect(
      screen.queryByRole("combobox", { name: "Sync interval" }),
    ).not.toBeInTheDocument()
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
    await user.click(screen.getByRole("tab", { name: "Seer" }))
    expect(screen.getByPlaceholderText("http://host:port")).toHaveValue(
      "http://js:5055",
    )
    expect(screen.getByText("Checking…")).toBeInTheDocument()
  })

  it("shows a service without a key as not set", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Sonarr" }))
    expect(screen.getByText("Set key")).toBeInTheDocument()
    expect(screen.getAllByText("Not set").length).toBeGreaterThan(0)
  })

  it("falls back gracefully when the services query has no data", async () => {
    vi.mocked(useServiceSettings).mockReturnValue(
      queryResult<ServicesSettings>(undefined),
    )
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Radarr" }))
    expect(screen.getByText("Set key")).toBeInTheDocument()
    expect(
      screen.getByPlaceholderText("http://host:port"),
    ).toBeInTheDocument()
  })

  it("shows a saving hint while the service update is pending", async () => {
    const user = userEvent.setup()
    const { rerender } = render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Seer" }))
    vi.mocked(useUpdateServiceSettings).mockReturnValue(
      mutation(serviceUpdateMutate, true),
    )
    rerender(<Settings />)
    expect(screen.getByText("Saving…")).toBeInTheDocument()
  })

  it("hydrates the saved service URL and leaves the API key input blank", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Seer" }))
    expect(screen.getByPlaceholderText("http://host:port")).toHaveValue(
      "http://js:5055",
    )
    expect(screen.getByPlaceholderText("Leave blank to keep current")).toHaveValue(
      "",
    )
  })

  it("does not autosave a service on initial render", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Radarr" }))
    expect(serviceUpdateMutate).not.toHaveBeenCalled()
  })

  it("autosaves a service URL and key after debounce", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Radarr" }))
    vi.useFakeTimers()

    act(() => {
      fireEvent.change(screen.getByPlaceholderText("http://host:port"), {
        target: { value: "http://radarr:7878" },
      })
      fireEvent.change(
        screen.getByPlaceholderText("Leave blank to keep current"),
        { target: { value: "rk" } },
      )
    })
    expect(serviceUpdateMutate).not.toHaveBeenCalled()

    act(() => vi.advanceTimersByTime(800))
    expect(serviceUpdateMutate).toHaveBeenCalledTimes(1)
    expect(serviceUpdateMutate).toHaveBeenCalledWith({
      name: "radarr",
      body: { url: "http://radarr:7878", api_key: "rk" },
    })

    vi.useRealTimers()
  })

  it("does not leak one service's URL into another service's tab", async () => {
    const user = userEvent.setup()
    render(<Settings />)

    await user.click(screen.getByRole("tab", { name: "Seer" }))
    expect(screen.getByPlaceholderText("http://host:port")).toHaveValue(
      "http://js:5055",
    )

    await user.click(screen.getByRole("tab", { name: "Sonarr" }))
    expect(screen.getByPlaceholderText("http://host:port")).toHaveValue("")
  })

  it("tests a service connection", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Seer" }))
    await user.click(screen.getByRole("button", { name: "Test connection" }))
    expect(serviceTestMutate).toHaveBeenCalledWith("seer")
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
    expect(screen.getByText("Set key")).toBeInTheDocument()
  })

  it("autosaves only the API key for an API-key-only service", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "TMDB" }))
    vi.useFakeTimers()

    act(() =>
      fireEvent.change(
        screen.getByPlaceholderText("Leave blank to keep current"),
        { target: { value: "tk" } },
      ),
    )
    expect(serviceUpdateMutate).not.toHaveBeenCalled()

    act(() => vi.advanceTimersByTime(800))
    expect(serviceUpdateMutate).toHaveBeenCalledWith({
      name: "tmdb",
      body: { api_key: "tk" },
    })

    vi.useRealTimers()
  })

  it("renders qBittorrent with url and api key and no stored secret", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "qBittorrent" }))
    expect(screen.getByText("URL")).toBeInTheDocument()
    expect(screen.getByText("API key")).toBeInTheDocument()
    expect(screen.getByText("Set key")).toBeInTheDocument()
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
    expect(screen.getByPlaceholderText("http://host:port")).toHaveValue(
      "http://qb:8080",
    )
    expect(screen.getByText("Checking…")).toBeInTheDocument()
    expect(screen.getAllByText("Saved").length).toBeGreaterThan(0)
  })

  it("falls back gracefully for qBittorrent when the query has no data", async () => {
    vi.mocked(useServiceSettings).mockReturnValue(
      queryResult<ServicesSettings>(undefined),
    )
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "qBittorrent" }))
    expect(screen.getByText("Set key")).toBeInTheDocument()
    expect(screen.getByPlaceholderText("http://host:port")).toBeInTheDocument()
    expect(
      screen.getByPlaceholderText("Leave blank to keep current"),
    ).toBeInTheDocument()
  })

  it("autosaves the URL and API key for qBittorrent", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "qBittorrent" }))
    vi.useFakeTimers()

    act(() => {
      fireEvent.change(screen.getByPlaceholderText("http://host:port"), {
        target: { value: "http://qb:8080" },
      })
      fireEvent.change(
        screen.getByPlaceholderText("Leave blank to keep current"),
        { target: { value: "qbt_key" } },
      )
    })
    expect(serviceUpdateMutate).not.toHaveBeenCalled()

    act(() => vi.advanceTimersByTime(800))
    expect(serviceUpdateMutate).toHaveBeenCalledWith({
      name: "qbittorrent",
      body: { url: "http://qb:8080", api_key: "qbt_key" },
    })

    vi.useRealTimers()
  })

  it("does not autosave qBittorrent when nothing changed", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "qBittorrent" }))
    vi.useFakeTimers()

    act(() => vi.advanceTimersByTime(800))
    expect(serviceUpdateMutate).not.toHaveBeenCalled()

    vi.useRealTimers()
  })

  it("does not send duplicate URL-only service saves while pending", async () => {
    const { rerender } = render(<Settings />)
    await userEvent.click(screen.getByRole("tab", { name: "Sonarr" }))
    vi.useFakeTimers()

    act(() =>
      fireEvent.change(screen.getByPlaceholderText("http://host:port"), {
        target: { value: "http://sonarr:8989" },
      }),
    )
    act(() => vi.advanceTimersByTime(800))
    expect(serviceUpdateMutate).toHaveBeenCalledTimes(1)
    expect(serviceUpdateMutate).toHaveBeenLastCalledWith({
      name: "sonarr",
      body: { url: "http://sonarr:8989" },
    })

    vi.mocked(useUpdateServiceSettings).mockReturnValue(
      mutation(serviceUpdateMutate, true),
    )
    rerender(<Settings />)

    act(() => vi.advanceTimersByTime(800))
    expect(serviceUpdateMutate).toHaveBeenCalledTimes(1)

    vi.useRealTimers()
  })

  it("does not send duplicate API-key-only service saves while pending", async () => {
    const { rerender } = render(<Settings />)
    await userEvent.click(screen.getByRole("tab", { name: "TMDB" }))
    vi.useFakeTimers()

    act(() =>
      fireEvent.change(
        screen.getByPlaceholderText("Leave blank to keep current"),
        { target: { value: "tmdb_key" } },
      ),
    )
    act(() => vi.advanceTimersByTime(800))
    expect(serviceUpdateMutate).toHaveBeenCalledTimes(1)
    expect(serviceUpdateMutate).toHaveBeenLastCalledWith({
      name: "tmdb",
      body: { api_key: "tmdb_key" },
    })

    vi.mocked(useUpdateServiceSettings).mockReturnValue(
      mutation(serviceUpdateMutate, true),
    )
    rerender(<Settings />)

    act(() => vi.advanceTimersByTime(800))
    expect(serviceUpdateMutate).toHaveBeenCalledTimes(1)

    vi.useRealTimers()
  })

  it("does not send duplicate URL+API-key service saves while pending", async () => {
    const { rerender } = render(<Settings />)
    await userEvent.click(screen.getByRole("tab", { name: "qBittorrent" }))
    vi.useFakeTimers()

    act(() => {
      fireEvent.change(screen.getByPlaceholderText("http://host:port"), {
        target: { value: "http://qb:8080" },
      })
      fireEvent.change(
        screen.getByPlaceholderText("Leave blank to keep current"),
        { target: { value: "qbt_key" } },
      )
    })
    act(() => vi.advanceTimersByTime(800))
    expect(serviceUpdateMutate).toHaveBeenCalledTimes(1)
    expect(serviceUpdateMutate).toHaveBeenLastCalledWith({
      name: "qbittorrent",
      body: { url: "http://qb:8080", api_key: "qbt_key" },
    })

    vi.mocked(useUpdateServiceSettings).mockReturnValue(
      mutation(serviceUpdateMutate, true),
    )
    rerender(<Settings />)

    act(() => vi.advanceTimersByTime(800))
    expect(serviceUpdateMutate).toHaveBeenCalledTimes(1)

    vi.useRealTimers()
  })

  it("does not retry a failed service save until a further edit", async () => {
    // Suppress onSuccess so the dirty draft survives the first submission,
    // simulating a failed save that settles back to non-pending.
    vi.mocked(useUpdateServiceSettings).mockReturnValue(
      mutation(serviceUpdateMutate, false, undefined, false),
    )
    const { rerender } = render(<Settings />)
    await userEvent.click(screen.getByRole("tab", { name: "qBittorrent" }))
    vi.useFakeTimers()

    act(() => {
      fireEvent.change(screen.getByPlaceholderText("http://host:port"), {
        target: { value: "http://qb:8080" },
      })
      fireEvent.change(
        screen.getByPlaceholderText("Leave blank to keep current"),
        { target: { value: "qbt_key" } },
      )
    })
    act(() => vi.advanceTimersByTime(800))
    expect(serviceUpdateMutate).toHaveBeenCalledTimes(1)

    // Mutation enters pending state.
    vi.mocked(useUpdateServiceSettings).mockReturnValue(
      mutation(serviceUpdateMutate, true),
    )
    rerender(<Settings />)

    act(() => vi.advanceTimersByTime(800))
    expect(serviceUpdateMutate).toHaveBeenCalledTimes(1)

    // Mutation fails/settles back to non-pending without calling onSuccess;
    // the dirty body must not be re-submitted automatically.
    vi.mocked(useUpdateServiceSettings).mockReturnValue(
      mutation(serviceUpdateMutate, false, undefined, false),
    )
    rerender(<Settings />)

    act(() => vi.advanceTimersByTime(800))
    expect(serviceUpdateMutate).toHaveBeenCalledTimes(1)

    act(() =>
      fireEvent.change(
        screen.getByPlaceholderText("Leave blank to keep current"),
        { target: { value: "qbt_key_after_failure" } },
      ),
    )
    act(() => vi.advanceTimersByTime(800))
    expect(serviceUpdateMutate).toHaveBeenCalledTimes(2)
    expect(serviceUpdateMutate).toHaveBeenLastCalledWith({
      name: "qbittorrent",
      body: { url: "http://qb:8080", api_key: "qbt_key_after_failure" },
    })

    vi.useRealTimers()
  })

  it("shows a configured service as Connected when the snapshot is ok", async () => {
    vi.mocked(useServiceStatuses).mockReturnValue(
      queryResult<ServicesStatusResponse>({
        interval_seconds: 60,
        last_check_at: "2026-06-27T12:00:00Z",
        services: { seer: { ok: true, detail: "Reachable", checked_at: "2026-06-27T12:00:00Z" } },
      }),
    )
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Seer" }))
    const badge = screen.getByText("Connected")
    expect(badge).toHaveClass("border-emerald-500/40")
    expect(badge).toHaveAttribute("title", "Reachable")
  })

  it("shows a configured service as Offline when the snapshot reports down", async () => {
    vi.mocked(useServiceStatuses).mockReturnValue(
      queryResult<ServicesStatusResponse>({
        interval_seconds: 60,
        last_check_at: "2026-06-27T12:00:00Z",
        services: {
          seer: { ok: false, detail: "Connection refused", checked_at: "2026-06-27T12:00:00Z" },
        },
      }),
    )
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Seer" }))
    const badge = screen.getByText("Offline")
    expect(badge).toHaveClass("border-red-500/40")
    expect(badge).toHaveAttribute("title", "Connection refused")
  })

  it("shows a configured service as Checking before the first status snapshot", async () => {
    vi.mocked(useServiceStatuses).mockReturnValue(
      queryResult<ServicesStatusResponse>({
        interval_seconds: 60,
        last_check_at: null,
        services: {},
      }),
    )
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Seer" }))
    const badge = screen.getByText("Checking…")
    expect(badge).toHaveClass("border-slate-500/40")
  })

  it("shows an unconfigured service as Set key regardless of the status snapshot", async () => {
    vi.mocked(useServiceStatuses).mockReturnValue(
      queryResult<ServicesStatusResponse>({
        interval_seconds: 60,
        last_check_at: "2026-06-27T12:00:00Z",
        services: { sonarr: { ok: true, detail: "Reachable", checked_at: "2026-06-27T12:00:00Z" } },
      }),
    )
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "Sonarr" }))
    const badge = screen.getByText("Set key")
    expect(badge).toHaveClass("border-amber-500/40")
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

describe("Settings — database", () => {
  it("renders the database tab and shows stats", async () => {
    await renderDatabase()
    expect(screen.getByRole("tab", { name: "Database" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(screen.getByText("1.0 KB")).toBeInTheDocument()
    expect(screen.getByText("2.0 KB")).toBeInTheDocument()
    expect(screen.getByText("5")).toBeInTheDocument()
    expect(screen.getByText("12")).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
  })

  it("shows a loading state while stats load", async () => {
    vi.mocked(useDatabaseStats).mockReturnValue(
      queryResult<typeof DATABASE_STATS>(undefined, true),
    )
    await renderDatabase()
    expect(screen.getByText("Loading…")).toBeInTheDocument()
  })

  async function confirmClearAction(user: ReturnType<typeof userEvent.setup>, buttonName: string) {
    await user.click(screen.getByRole("button", { name: buttonName }))
    await user.click(screen.getByRole("button", { name: "Clear" }))
  }

  it("confirms and clears the activity log", async () => {
    const user = await renderDatabase()
    await confirmClearAction(user, "Clear activity log")
    expect(clearActivityMutate).toHaveBeenCalledTimes(1)
  })

  it("confirms and clears synced items & sync state", async () => {
    const user = await renderDatabase()
    await confirmClearAction(user, "Clear synced items & sync state")
    expect(clearItemsMutate).toHaveBeenCalledTimes(1)
  })

  it("confirms and clears the poster cache", async () => {
    const user = await renderDatabase()
    await confirmClearAction(user, "Clear poster cache")
    expect(clearPostersMutate).toHaveBeenCalledTimes(1)
  })

  it("disables a clear button while its mutation is pending", async () => {
    vi.mocked(useClearActivity).mockReturnValue(mutation(clearActivityMutate, true))
    await renderDatabase()
    expect(screen.getByRole("button", { name: "Clear activity log" })).toBeDisabled()
  })

  it("persists the Database tab to localStorage", async () => {
    await renderDatabase()
    expect(localStorage.getItem(SETTINGS_TAB_STORAGE_KEY)).toBe("database")
  })
})
