import { render as rtlRender, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { MemoryRouter } from "react-router-dom"
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type Mock,
} from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useRemindarrStatus: vi.fn(),
  useRemindarrResults: vi.fn(),
  useRemindarrTags: vi.fn(),
  useRemindarrSettings: vi.fn(),
  useRunRemindarr: vi.fn(),
  useUpdateRemindarrSettings: vi.fn(),
}))

import { Remindarr } from "@/features/remindarr/Remindarr"
import { intervalLabel } from "@/features/remindarr/labels"
import { REMINDARR_TAB_STORAGE_KEY } from "@/features/remindarr/remindarr-tab"
import { SETTINGS_TAB_STORAGE_KEY } from "@/features/settings/settings-tab"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import type {
  RemindarrResults,
  RemindarrSeriesGroup,
  RemindarrSettings,
  RemindarrSettingsUpdate,
  RemindarrStatus,
  RemindarrTag,
} from "@/shared/lib/api"
import {
  useRemindarrResults,
  useRemindarrSettings,
  useRemindarrStatus,
  useRemindarrTags,
  useRunRemindarr,
  useUpdateRemindarrSettings,
} from "@/shared/lib/queries"
import { mutationResult, queryResult } from "@/shared/test/mock-query"

const SETTINGS: RemindarrSettings = {
  enabled: true,
  interval_minutes: 60,
  tag_ids: [1, 2],
  monitored_only: true,
}

const TAGS: RemindarrTag[] = [
  { id: 1, label: "anime" },
  { id: 3, label: "kids" },
  { id: 2, label: "watch-together" },
]

const STATUS: RemindarrStatus = {
  settings: SETTINGS,
  running: false,
  plex_configured: true,
  last_success_at: "2026-11-21T09:00:00Z",
  last_attempt_at: "2026-11-21T09:00:00Z",
  last_error: null,
  stale: false,
  missing_tag_ids: [],
  counts: {
    unwatched: 3,
    series_with_unwatched: 2,
    tracked_series: 4,
    unmatched_series: 2,
  },
}

function group(
  seriesId: number,
  title: string,
  overrides: Partial<RemindarrSeriesGroup> = {},
): RemindarrSeriesGroup {
  return {
    series_id: seriesId,
    series_title: title,
    series_slug: null,
    tvdb_id: 1000 + seriesId,
    episodes_not_in_plex: 0,
    latest_added_at: "2026-11-21T06:00:00Z",
    new_today: 0,
    episodes: [
      {
        episode_id: seriesId * 10,
        series_id: seriesId,
        episode_file_id: seriesId * 100,
        season_number: 1,
        episode_number: 4,
        label: "S01E04",
        title: "The Lighthouse Log",
        air_date_utc: "2026-11-12T00:00:00Z",
        added_at: "2026-11-18T06:00:00Z",
        new_today: false,
      },
    ],
    ...overrides,
  }
}

const RESULTS: RemindarrResults = {
  last_success_at: "2026-11-21T09:00:00Z",
  series: [
    group(1, "Starfall Academy", {
      episodes_not_in_plex: 1,
      new_today: 1,
      episodes: [
        {
          episode_id: 11,
          series_id: 1,
          episode_file_id: 111,
          season_number: 3,
          episode_number: 8,
          label: "S03E08",
          title: "The Second Trial",
          air_date_utc: "2026-11-20T00:00:00Z",
          added_at: "2026-11-21T06:00:00Z",
          new_today: true,
        },
        {
          episode_id: 12,
          series_id: 1,
          episode_file_id: 112,
          season_number: 3,
          episode_number: 7,
          label: "S03E07",
          title: "",
          air_date_utc: null,
          added_at: null,
          new_today: false,
        },
      ],
    }),
    group(2, "Harbour Lights", { episodes_not_in_plex: 3 }),
    group(5, "Quiet Hours"),
  ],
  unmatched: [
    {
      series_id: 3,
      series_title: "Moonlit Rivers",
      series_slug: null,
      tvdb_id: 103,
      reason: "not_in_plex",
      reason_label: "No Plex show with this TVDB id",
    },
    {
      series_id: 4,
      series_title: "Paper Cranes (2025)",
      series_slug: null,
      tvdb_id: null,
      reason: "no_tvdb_id",
      reason_label: "No TVDB id in Sonarr",
    },
  ],
}

const EMPTY_RESULTS: RemindarrResults = {
  last_success_at: null,
  series: [],
  unmatched: [],
}

let runMutate: Mock<(variables: void) => void>
let saveMutate: Mock<(update: RemindarrSettingsUpdate) => void>

function render(ui: ReactElement) {
  return rtlRender(
    <MemoryRouter>
      <TooltipProvider>{ui}</TooltipProvider>
    </MemoryRouter>,
  )
}

function status(overrides: Partial<RemindarrStatus> = {}): RemindarrStatus {
  return { ...STATUS, ...overrides }
}

function withStatus(overrides: Partial<RemindarrStatus>) {
  vi.mocked(useRemindarrStatus).mockReturnValue(queryResult(status(overrides)))
}

beforeEach(() => {
  localStorage.clear()
  runMutate = vi.fn()
  saveMutate = vi.fn()
  vi.mocked(useRemindarrStatus).mockReturnValue(queryResult(STATUS))
  vi.mocked(useRemindarrResults).mockReturnValue(queryResult(RESULTS))
  vi.mocked(useRemindarrTags).mockReturnValue(queryResult(TAGS))
  vi.mocked(useRemindarrSettings).mockReturnValue(queryResult(SETTINGS))
  vi.mocked(useRunRemindarr).mockReturnValue(mutationResult(runMutate))
  vi.mocked(useUpdateRemindarrSettings).mockReturnValue(
    mutationResult(saveMutate),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("Remindarr page", () => {
  it("defaults to Reminders and persists the selected tab", async () => {
    const user = userEvent.setup()
    render(<Remindarr />)
    expect(
      screen.getByRole("heading", { name: "Remindarr", level: 1 }),
    ).toBeInTheDocument()
    expect(screen.getByText("Series with reminders")).toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: /settings/i }))
    expect(localStorage.getItem(REMINDARR_TAB_STORAGE_KEY)).toBe("settings")
    expect(screen.getByText("Remindarr settings")).toBeInTheDocument()
    await user.click(screen.getByRole("tab", { name: /reminders/i }))
    expect(localStorage.getItem(REMINDARR_TAB_STORAGE_KEY)).toBe("reminders")
  })

  it("restores a valid stored tab and ignores invalid storage", () => {
    localStorage.setItem(REMINDARR_TAB_STORAGE_KEY, "settings")
    const { unmount } = render(<Remindarr />)
    expect(screen.getByText("Remindarr settings")).toBeInTheDocument()
    unmount()

    localStorage.setItem(REMINDARR_TAB_STORAGE_KEY, "bad")
    render(<Remindarr />)
    expect(screen.getByText("Series with reminders")).toBeInTheDocument()
  })

  it("works without localStorage", async () => {
    vi.stubGlobal("localStorage", undefined)
    const user = userEvent.setup()
    render(<Remindarr />)
    await user.click(screen.getByRole("tab", { name: /settings/i }))
    expect(screen.getByText("Remindarr settings")).toBeInTheDocument()
  })
})

describe("Reminders tab", () => {
  it("shows the stats, scope, series groups and unmatched series", () => {
    render(<Remindarr />)

    // The stat block and the card title both read "Unwatched episodes".
    expect(screen.getAllByText("Unwatched episodes")).toHaveLength(2)
    expect(screen.getByText("Not found in Plex")).toBeInTheDocument()
    expect(screen.getByText("Last refresh")).toBeInTheDocument()
    expect(
      screen.getByText(
        "Downloaded, monitored episodes of monitored series tagged anime or watch-together that the Plex token owner has not watched. Refreshes every 1 hour.",
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText("4 series tracked, 3 unwatched episodes"),
    ).toBeInTheDocument()

    const starfall = screen.getByRole("region", { name: "Starfall Academy" })
    expect(within(starfall).getByText("2 unwatched")).toBeInTheDocument()
    expect(
      within(starfall).getByText("1 episode not in Plex yet"),
    ).toBeInTheDocument()
    expect(within(starfall).getByText("S03E08")).toBeInTheDocument()
    expect(within(starfall).getByText("New today")).toBeInTheDocument()
    expect(within(starfall).getByText("New today").closest("tr")).toHaveClass(
      "bg-muted/60",
    )
    // A missing air date shows an em dash; an untitled episode no separator.
    expect(within(starfall).getByText("—")).toBeInTheDocument()
    expect(
      within(starfall).getByText("S03E07").parentElement,
    ).toHaveTextContent(/^S03E07$/)

    // Groups without a new-today episode (other than the newest) start closed.
    const harbour = screen.getByRole("region", { name: "Harbour Lights" })
    expect(
      within(harbour).getByText("3 episodes not in Plex yet"),
    ).toBeInTheDocument()
    expect(within(harbour).queryByText("S01E04")).not.toBeInTheDocument()

    // Every episode of this matched series is in Plex: no "not in Plex" note.
    const quiet = screen.getByRole("region", { name: "Quiet Hours" })
    expect(within(quiet).queryByText(/not in Plex/)).not.toBeInTheDocument()

    expect(screen.getByText("Not found in Plex (2)")).toBeInTheDocument()
    expect(
      screen.getByText("No Plex show with this TVDB id"),
    ).toBeInTheDocument()
    expect(screen.getByText("No TVDB id in Sonarr")).toBeInTheDocument()
  })

  it("expands and collapses a series group", async () => {
    const user = userEvent.setup()
    render(<Remindarr />)
    const harbour = screen.getByRole("region", { name: "Harbour Lights" })
    await user.click(
      within(harbour).getByRole("button", { name: "Expand Harbour Lights" }),
    )
    expect(within(harbour).getByText("S01E04")).toBeInTheDocument()
    await user.click(
      within(harbour).getByRole("button", { name: "Collapse Harbour Lights" }),
    )
    expect(within(harbour).queryByText("S01E04")).not.toBeInTheDocument()
  })

  it("refreshes on demand", async () => {
    const user = userEvent.setup()
    render(<Remindarr />)
    await user.click(screen.getByRole("button", { name: "Refresh now" }))
    expect(runMutate).toHaveBeenCalledTimes(1)
  })

  it("describes the scope without monitoring and with an unknown tag", () => {
    withStatus({
      settings: {
        ...SETTINGS,
        monitored_only: false,
        tag_ids: [7],
        interval_minutes: 1440,
      },
    })
    vi.mocked(useRemindarrTags).mockReturnValue(
      queryResult<RemindarrTag[]>(undefined),
    )
    render(<Remindarr />)
    expect(
      screen.getByText(
        "Downloaded episodes of series tagged tag 7 that the Plex token owner has not watched. Refreshes every 1 day.",
      ),
    ).toBeInTheDocument()
  })

  it("shows the stale banner with the kept results' time", () => {
    withStatus({
      stale: true,
      last_error: "Plex rejected the token.",
      last_attempt_at: new Date(Date.now() - 12 * 60_000).toISOString(),
    })
    render(<Remindarr />)
    const alert = screen.getByRole("alert")
    expect(
      within(alert).getByText("Results may be out of date"),
    ).toBeInTheDocument()
    expect(alert).toHaveTextContent(
      /Last refresh failed 12 min ago: Plex rejected the token; showing results from /,
    )
  })

  it("shows the stale banner before any successful refresh", () => {
    withStatus({
      stale: true,
      last_error: "Plex is not connected",
      last_attempt_at: null,
      last_success_at: null,
    })
    vi.mocked(useRemindarrResults).mockReturnValue(queryResult(EMPTY_RESULTS))
    render(<Remindarr />)
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Last refresh failed: Plex is not connected.",
    )
    expect(screen.getByText("Never")).toBeInTheDocument()
  })

  it("links to the Plex settings when Plex is not connected", async () => {
    withStatus({ plex_configured: false })
    const user = userEvent.setup()
    render(<Remindarr />)
    expect(screen.getByRole("button", { name: "Refresh now" })).toBeDisabled()
    const link = screen.getByRole("link", { name: "Set up Plex in Settings" })
    expect(link).toHaveAttribute("href", "/settings")
    await user.click(link)
    expect(localStorage.getItem(SETTINGS_TAB_STORAGE_KEY)).toBe("plex")
  })

  it("follows the Plex link without localStorage", async () => {
    withStatus({ plex_configured: false })
    vi.stubGlobal("localStorage", undefined)
    const user = userEvent.setup()
    render(<Remindarr />)
    await user.click(
      screen.getByRole("link", { name: "Set up Plex in Settings" }),
    )
  })

  it("disables refresh with a hint while Remindarr is disabled", () => {
    withStatus({ settings: { ...SETTINGS, enabled: false } })
    render(<Remindarr />)
    expect(screen.getByRole("button", { name: "Refresh now" })).toBeDisabled()
    expect(
      screen.getByText("Enable Remindarr on the Settings tab to refresh."),
    ).toBeInTheDocument()
  })

  it.each([
    ["the backend reports a refresh", { running: true }, false],
    ["the manual refresh is pending", {}, true],
  ])("shows a running refresh when %s", (_case, overrides, pending) => {
    withStatus(overrides)
    vi.mocked(useRunRemindarr).mockReturnValue(
      mutationResult(runMutate, pending),
    )
    render(<Remindarr />)
    expect(screen.getByRole("button", { name: "Refreshing" })).toBeDisabled()
    expect(
      screen.getByText("A refresh is already running."),
    ).toBeInTheDocument()
  })

  it.each([
    [
      "no tags are selected",
      { settings: { ...SETTINGS, tag_ids: [] } },
      "Choose at least one Sonarr tag on the Settings tab to start tracking series.",
    ],
    [
      "it has never run",
      { last_success_at: null },
      "Refresh now to list the episodes you have not watched yet.",
    ],
    [
      "nothing is unwatched",
      {},
      "You are up to date: every downloaded episode of your tagged series has been watched in Plex.",
    ],
  ])("explains the empty state when %s", (_case, overrides, text) => {
    withStatus(overrides)
    vi.mocked(useRemindarrResults).mockReturnValue(queryResult(EMPTY_RESULTS))
    render(<Remindarr />)
    expect(screen.getByText(text)).toBeInTheDocument()
    expect(screen.queryByText(/Not found in Plex \(/)).not.toBeInTheDocument()
  })

  const UNKNOWN_WATCH_STATE =
    "Nothing unwatched in Plex. The episodes and series below are not in Plex yet, so their watch state is unknown."
  const UP_TO_DATE =
    "You are up to date: every downloaded episode of your tagged series has been watched in Plex."

  it.each([
    ["watched plus missing", 1, "1 episode not in Plex yet"],
    ["all missing", 3, "3 episodes not in Plex yet"],
  ])(
    "keeps a series with no unwatched episodes visible when %s",
    (_case, missing, note) => {
      withStatus({
        counts: { ...STATUS.counts, unwatched: 0, series_with_unwatched: 0 },
      })
      vi.mocked(useRemindarrResults).mockReturnValue(
        queryResult<RemindarrResults>({
          ...EMPTY_RESULTS,
          last_success_at: STATUS.last_success_at,
          series: [
            group(1, "Starfall Academy", {
              episodes_not_in_plex: missing,
              episodes: [],
            }),
          ],
        }),
      )
      render(<Remindarr />)

      const starfall = screen.getByRole("region", { name: "Starfall Academy" })
      expect(within(starfall).getByText(note)).toBeInTheDocument()
      expect(within(starfall).queryByText(/unwatched$/)).not.toBeInTheDocument()
      expect(
        within(starfall).getByText(
          "Every episode Plex lists has been watched. Plex does not list the rest yet, so their watch state is unknown.",
        ),
      ).toBeInTheDocument()
      expect(within(starfall).queryByRole("table")).not.toBeInTheDocument()
      expect(screen.getByText(UNKNOWN_WATCH_STATE)).toBeInTheDocument()
      expect(screen.queryByText(UP_TO_DATE)).not.toBeInTheDocument()
    },
  )

  it("does not call unmatched-only results up to date", () => {
    withStatus({
      counts: { ...STATUS.counts, unwatched: 0, series_with_unwatched: 0 },
    })
    vi.mocked(useRemindarrResults).mockReturnValue(
      queryResult<RemindarrResults>({ ...RESULTS, series: [] }),
    )
    render(<Remindarr />)
    expect(screen.getByText(UNKNOWN_WATCH_STATE)).toBeInTheDocument()
    expect(screen.queryByText(UP_TO_DATE)).not.toBeInTheDocument()
    expect(screen.getByText("Not found in Plex (2)")).toBeInTheDocument()
  })

  it("shows no empty state beside unwatched episodes", () => {
    render(<Remindarr />)
    expect(screen.queryByText(UNKNOWN_WATCH_STATE)).not.toBeInTheDocument()
    expect(screen.queryByText(UP_TO_DATE)).not.toBeInTheDocument()
  })

  it("hides the tracked summary before the first refresh", () => {
    withStatus({ last_success_at: null })
    render(<Remindarr />)
    expect(screen.queryByText(/series tracked/)).not.toBeInTheDocument()
  })

  it("shows loading while either query loads", () => {
    vi.mocked(useRemindarrResults).mockReturnValue(
      queryResult<RemindarrResults>(undefined, true),
    )
    render(<Remindarr />)
    expect(screen.getByText("Loading reminders…")).toBeInTheDocument()
  })

  it("shows a load error", () => {
    vi.mocked(useRemindarrStatus).mockReturnValue(
      queryResult<RemindarrStatus>(undefined, false, {
        error: new Error("Remindarr unavailable"),
      }),
    )
    render(<Remindarr />)
    expect(
      screen.getByText("Could not load Remindarr: Remindarr unavailable"),
    ).toBeInTheDocument()
  })

  it("reports a failed status while the results wait for it", () => {
    vi.mocked(useRemindarrStatus).mockReturnValue(
      queryResult<RemindarrStatus>(undefined, false, {
        error: new Error("Remindarr unavailable"),
      }),
    )
    // The results query is disabled until a status arrives: pending for good.
    vi.mocked(useRemindarrResults).mockReturnValue(
      queryResult<RemindarrResults>(undefined, false, { isPending: true }),
    )
    render(<Remindarr />)
    expect(
      screen.getByText("Could not load Remindarr: Remindarr unavailable"),
    ).toBeInTheDocument()
    expect(screen.queryByText("Loading reminders…")).not.toBeInTheDocument()
  })

  it("reports missing data without an error", () => {
    vi.mocked(useRemindarrResults).mockReturnValue(
      queryResult<RemindarrResults>(undefined),
    )
    render(<Remindarr />)
    expect(
      screen.getByText("Could not load Remindarr: no data"),
    ).toBeInTheDocument()
  })
})

describe("Settings tab", () => {
  beforeEach(() => {
    localStorage.setItem(REMINDARR_TAB_STORAGE_KEY, "settings")
  })

  it("shows loading until the settings arrive", () => {
    vi.mocked(useRemindarrSettings).mockReturnValue(
      queryResult<RemindarrSettings>(undefined, true),
    )
    render(<Remindarr />)
    expect(screen.getByText("Loading Remindarr settings…")).toBeInTheDocument()
  })

  it("shows a failed settings load with a retry", async () => {
    const refetch = vi.fn().mockResolvedValue(undefined)
    vi.mocked(useRemindarrSettings).mockReturnValue(
      queryResult<RemindarrSettings>(undefined, false, {
        isError: true,
        error: new Error("offline"),
        isFetching: false,
        refetch,
      }),
    )
    const user = userEvent.setup()
    render(<Remindarr />)

    expect(
      screen.getByText("Could not load Remindarr settings: offline"),
    ).toBeInTheDocument()
    expect(
      screen.queryByText("Loading Remindarr settings…"),
    ).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Try again" }))
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it("disables the retry while it is fetching", () => {
    vi.mocked(useRemindarrSettings).mockReturnValue(
      queryResult<RemindarrSettings>(undefined, false, {
        isError: true,
        error: new Error("offline"),
        isFetching: true,
      }),
    )
    render(<Remindarr />)
    expect(screen.getByRole("button", { name: "Try again" })).toBeDisabled()
  })

  it("keeps the form when a background refetch fails", () => {
    vi.mocked(useRemindarrSettings).mockReturnValue(
      queryResult(SETTINGS, false, {
        isError: true,
        error: new Error("offline"),
      }),
    )
    render(<Remindarr />)
    expect(screen.getByText("Remindarr settings")).toBeInTheDocument()
    expect(
      screen.queryByText("Could not load Remindarr settings: offline"),
    ).not.toBeInTheDocument()
  })

  it("lists live tags and keeps a saved tag Sonarr no longer reports", () => {
    vi.mocked(useRemindarrSettings).mockReturnValue(
      queryResult({ ...SETTINGS, tag_ids: [1, 7] }),
    )
    render(<Remindarr />)
    const group = screen.getByRole("group", { name: "Sonarr tags to track" })
    expect(within(group).getByLabelText("anime")).toBeChecked()
    expect(within(group).getByLabelText("kids")).not.toBeChecked()
    expect(within(group).getByLabelText("watch-together")).not.toBeChecked()
    expect(within(group).getByText("tag 7")).toBeInTheDocument()
    expect(within(group).getByText("(not in Sonarr)")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled()
  })

  it("does not flag saved tags while Sonarr's tags are unavailable", () => {
    vi.mocked(useRemindarrTags).mockReturnValue(
      queryResult<RemindarrTag[]>(undefined, false, {
        error: new Error("sonarr down"),
      }),
    )
    render(<Remindarr />)
    const group = screen.getByRole("group", { name: "Sonarr tags to track" })
    expect(within(group).getByText("tag 1")).toBeInTheDocument()
    expect(within(group).queryByText("(not in Sonarr)")).not.toBeInTheDocument()
    expect(
      within(group).getByText("Could not load Sonarr tags: sonarr down"),
    ).toBeInTheDocument()
  })

  it.each([
    [queryResult<RemindarrTag[]>(undefined, true), "Loading Sonarr tags…"],
    [queryResult<RemindarrTag[]>([]), "Sonarr reported no tags."],
  ])("shows the tag notice %#", (result, notice) => {
    vi.mocked(useRemindarrTags).mockReturnValue(result)
    render(<Remindarr />)
    expect(screen.getByText(notice)).toBeInTheDocument()
  })

  it("saves only the changed fields", async () => {
    const user = userEvent.setup()
    render(<Remindarr />)

    await user.click(
      screen.getByRole("switch", { name: "Run the scheduled refresh" }),
    )
    await user.click(
      screen.getByRole("switch", {
        name: "Monitored series and episodes only",
      }),
    )
    await user.click(screen.getByLabelText("kids"))
    await user.click(screen.getByLabelText("anime"))
    await user.click(screen.getByRole("combobox", { name: "Refresh interval" }))
    await user.click(screen.getByRole("option", { name: "6 hours" }))
    await user.click(screen.getByRole("button", { name: "Save" }))

    expect(saveMutate).toHaveBeenCalledWith({
      enabled: false,
      monitored_only: false,
      interval_minutes: 360,
      tag_ids: [2, 3],
    })
  })

  it("treats a reordered tag selection as unchanged", async () => {
    const user = userEvent.setup()
    render(<Remindarr />)
    await user.click(screen.getByLabelText("anime"))
    await user.click(screen.getByLabelText("anime"))
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled()
  })

  it("keeps a saved interval outside the offered options", async () => {
    vi.mocked(useRemindarrSettings).mockReturnValue(
      queryResult({ ...SETTINGS, interval_minutes: 45 }),
    )
    const user = userEvent.setup()
    render(<Remindarr />)
    const combobox = screen.getByRole("combobox", { name: "Refresh interval" })
    expect(combobox).toHaveTextContent("45 minutes")
    await user.click(combobox)
    const options = screen
      .getAllByRole("option")
      .map((option) => option.textContent)
    expect(options).toEqual([
      "15 minutes",
      "30 minutes",
      "45 minutes",
      "1 hour",
      "2 hours",
      "6 hours",
      "12 hours",
      "1 day",
    ])
  })

  it("disables the form while saving", () => {
    vi.mocked(useUpdateRemindarrSettings).mockReturnValue(
      mutationResult(saveMutate, true),
    )
    render(<Remindarr />)
    expect(
      screen.getByRole("switch", { name: "Run the scheduled refresh" }),
    ).toBeDisabled()
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled()
  })
})

describe("intervalLabel", () => {
  it.each([
    [1, "1 minute"],
    [15, "15 minutes"],
    [60, "1 hour"],
    [120, "2 hours"],
    [1440, "1 day"],
    [2880, "2 days"],
  ])("labels %i minutes as %s", (minutes, label) => {
    expect(intervalLabel(minutes)).toBe(label)
  })
})
