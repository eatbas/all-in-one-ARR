import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useLanguagarrStatus: vi.fn(),
  useLanguagarrResults: vi.fn(),
  useLanguagarrSettings: vi.fn(),
  useLanguagarrQueue: vi.fn(),
  useLanguagarrProfiles: vi.fn(),
  useLanguagarrLanguages: vi.fn(),
  useScanLanguagarr: vi.fn(),
  useEnqueueLanguagarr: vi.fn(),
  useDeleteLanguagarr: vi.fn(),
  useRunLanguagarr: vi.fn(),
  useClearLanguagarrPending: vi.fn(),
  useUpdateLanguagarrSettings: vi.fn(),
  useServiceSettings: vi.fn(),
}))

import { Languagarr } from "@/features/languagarr/Languagarr"
import { LANGUAGARR_TAB_STORAGE_KEY } from "@/features/languagarr/languagarr-tab"
import type {
  LanguagarrAudioLanguage,
  LanguagarrItem,
  LanguagarrQualityProfile,
  LanguagarrQueue,
  LanguagarrResults,
  LanguagarrScanSummary,
  LanguagarrSettings,
  LanguagarrStatus,
  ServicesSettings,
} from "@/shared/lib/api"
import {
  useClearLanguagarrPending,
  useDeleteLanguagarr,
  useEnqueueLanguagarr,
  useLanguagarrLanguages,
  useLanguagarrProfiles,
  useLanguagarrQueue,
  useLanguagarrResults,
  useLanguagarrSettings,
  useLanguagarrStatus,
  useRunLanguagarr,
  useScanLanguagarr,
  useServiceSettings,
  useUpdateLanguagarrSettings,
} from "@/shared/lib/queries"
import { mutationResult, queryResult } from "@/shared/test/mock-query"

const SETTINGS: LanguagarrSettings = {
  enabled: false,
  interval_minutes: 60,
  searches_per_run: 10,
  retry_after_hours: 168,
  auto_queue: false,
  monitored_only: true,
  quality_profile_names: ["Anime"],
  target_audio_languages: ["eng"],
  sonarr_link_url: "http://192.168.0.2:8989",
}

/** A slice of the language catalogue, in the backend's order. */
const LANGUAGES: LanguagarrAudioLanguage[] = [
  { code: "eng", name: "English" },
  { code: "jpn", name: "Japanese" },
  { code: "tur", name: "Turkish" },
]

/** Sonarr's profiles as the scope checklist receives them (sorted by name). */
const PROFILES: LanguagarrQualityProfile[] = [
  { id: 7, name: "Anime" },
  { id: 9, name: "Anime 4K" },
  { id: 4, name: "HD Bluray + WEB" },
]

/** Service settings whose Sonarr URL is `sonarrUrl`. */
function services(sonarrUrl: string): ServicesSettings {
  return { sonarr: { url: sonarrUrl } } as ServicesSettings
}

const SCAN: LanguagarrScanSummary = {
  is_scanning: false,
  last_scan_at: "2026-10-12T18:00:00Z",
  last_error: null,
  profiles_in_scope: ["Anime"],
  target_languages: ["eng"],
  series_scanned: 2,
  files_scanned: 10,
  non_compliant: 3,
  unknown: 1,
  missing_language: 3,
}

function item(
  id: number,
  overrides: Partial<LanguagarrItem> = {},
): LanguagarrItem {
  return {
    episode_file_id: id,
    series_id: 1,
    series_title: "Log Horizon",
    series_slug: "log-horizon",
    season_number: 1,
    episode_ids: [id * 10],
    episode_label: `S01E${String(id).padStart(2, "0")}`,
    relative_path: `Season 01/file-${id}.mkv`,
    audio_languages: "jpn/por",
    sonarr_languages: ["Japanese", "Portuguese"],
    verdict: "missing_language",
    release_group: "Anipakku",
    custom_format_score: -18000,
    cutoff_format_score: 10000,
    recommended_action: "search",
    queue_status: "none",
    last_searched_at: null,
    ...overrides,
  }
}

const RESULTS: LanguagarrResults = {
  scan: SCAN,
  results: [
    item(1),
    item(2, { queue_status: "pending" }),
    item(3, {
      series_id: 2,
      series_title: "My Hero Academia",
      series_slug: null,
      audio_languages: "jpn/jpn",
      verdict: "missing_language",
      release_group: null,
      custom_format_score: 12000,
      recommended_action: "delete_and_search",
    }),
  ],
  unknown: [
    item(9, {
      audio_languages: "",
      verdict: "unknown",
      relative_path: "Season 01/unknown.mkv",
    }),
  ],
}

const STATUS: LanguagarrStatus = {
  settings: SETTINGS,
  running: false,
  scan: SCAN,
  queue: { pending: 1, searched: 1, failed: 1 },
}

const QUEUE: LanguagarrQueue = {
  counts: { pending: 1, searched: 1, failed: 1 },
  rows: [
    {
      episode_file_id: 2,
      series_id: 1,
      series_slug: "log-horizon",
      title: "Log Horizon - S01E02",
      episode_ids: [20],
      reason: "missing_language",
      status: "pending",
      queued_at: "2026-10-12T18:00:00Z",
      searched_at: null,
      attempts: 0,
      last_error: null,
    },
    {
      episode_file_id: 4,
      series_id: 1,
      series_slug: null,
      title: "Log Horizon - S01E04",
      episode_ids: [40],
      reason: "missing_language",
      status: "searched",
      queued_at: "2026-10-12T17:00:00Z",
      searched_at: "2026-10-12T17:30:00Z",
      attempts: 1,
      last_error: null,
    },
    {
      episode_file_id: 5,
      series_id: 1,
      series_slug: null,
      title: "Log Horizon - S01E05",
      episode_ids: [50],
      reason: "legacy_reason",
      status: "failed",
      queued_at: "2026-10-12T16:00:00Z",
      searched_at: "2026-10-12T16:30:00Z",
      attempts: 2,
      last_error: "sonarr API request failed",
    },
  ],
}

/** A mutate mock that runs the caller's `onSuccess` like a real mutation. */
function succeedingMutate<TVariables>() {
  return vi.fn((_vars: TVariables, options?: { onSuccess?: () => void }) => {
    options?.onSuccess?.()
  })
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(useLanguagarrStatus).mockReturnValue(queryResult(STATUS))
  vi.mocked(useLanguagarrResults).mockReturnValue(queryResult(RESULTS))
  vi.mocked(useLanguagarrSettings).mockReturnValue(queryResult(SETTINGS))
  vi.mocked(useLanguagarrQueue).mockReturnValue(queryResult(QUEUE))
  vi.mocked(useLanguagarrProfiles).mockReturnValue(queryResult(PROFILES))
  vi.mocked(useLanguagarrLanguages).mockReturnValue(queryResult(LANGUAGES))
  vi.mocked(useScanLanguagarr).mockReturnValue(mutationResult(vi.fn()))
  vi.mocked(useEnqueueLanguagarr).mockReturnValue(mutationResult(vi.fn()))
  vi.mocked(useDeleteLanguagarr).mockReturnValue(mutationResult(vi.fn()))
  vi.mocked(useRunLanguagarr).mockReturnValue(mutationResult(vi.fn()))
  vi.mocked(useClearLanguagarrPending).mockReturnValue(mutationResult(vi.fn()))
  vi.mocked(useUpdateLanguagarrSettings).mockReturnValue(
    mutationResult(vi.fn()),
  )
  vi.mocked(useServiceSettings).mockReturnValue(
    queryResult(services("http://sonarr:8989")),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("Languagarr page", () => {
  it("defaults to Review and persists the selected tab", async () => {
    const user = userEvent.setup()
    render(<Languagarr />)
    expect(screen.getByText("Anime audio audit")).toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: /queue/i }))
    expect(localStorage.getItem(LANGUAGARR_TAB_STORAGE_KEY)).toBe("queue")
    await user.click(screen.getByRole("tab", { name: /settings/i }))
    expect(localStorage.getItem(LANGUAGARR_TAB_STORAGE_KEY)).toBe("settings")
  })

  it("restores a valid stored tab and ignores invalid storage", () => {
    localStorage.setItem(LANGUAGARR_TAB_STORAGE_KEY, "queue")
    const { unmount } = render(<Languagarr />)
    expect(screen.getByText("Run a batch now")).toBeInTheDocument()
    unmount()

    localStorage.setItem(LANGUAGARR_TAB_STORAGE_KEY, "bad")
    render(<Languagarr />)
    expect(screen.getByText("Anime audio audit")).toBeInTheDocument()
  })

  it("works without localStorage", async () => {
    vi.stubGlobal("localStorage", undefined)
    const user = userEvent.setup()
    render(<Languagarr />)
    await user.click(screen.getByRole("tab", { name: /queue/i }))
    expect(screen.getByText("Run a batch now")).toBeInTheDocument()
  })
})

describe("Languagarr review", () => {
  it("shows scan statistics, grouped results and unknown files", () => {
    render(<Languagarr />)
    expect(screen.getByText("Without English audio")).toBeInTheDocument()
    expect(screen.getByText("Files checked")).toBeInTheDocument()
    expect(screen.getByText("2 series, 10 files checked")).toBeInTheDocument()
    const logHorizon = screen.getByRole("region", { name: "Log Horizon" })
    expect(within(logHorizon).getByText("S01E01")).toBeInTheDocument()
    expect(within(logHorizon).getByText("Queued")).toBeInTheDocument()
    expect(within(logHorizon).getAllByText("Anipakku")).toHaveLength(2)
    const mha = screen.getByRole("region", { name: "My Hero Academia" })
    expect(within(mha).getByText("12000 / 10000")).toBeInTheDocument()
    expect(within(mha).getByText("—")).toBeInTheDocument()
    expect(within(mha).getAllByText("Delete & search").length).toBeGreaterThan(
      0,
    )
    expect(screen.getByText("Unknown audio (1)")).toBeInTheDocument()
    expect(
      screen.getByText("Log Horizon — Season 01/unknown.mkv"),
    ).toBeInTheDocument()
  })

  it("links each series to Sonarr through the configured link URL", () => {
    render(<Languagarr />)
    const logHorizon = screen.getByRole("region", { name: "Log Horizon" })
    const link = within(logHorizon).getByRole("link", {
      name: "Open Log Horizon in Sonarr",
    })
    expect(link).toHaveAttribute(
      "href",
      "http://192.168.0.2:8989/series/log-horizon",
    )
    expect(link).toHaveAttribute("target", "_blank")
    // A series Sonarr reported no slug for gets no link.
    const mha = screen.getByRole("region", { name: "My Hero Academia" })
    expect(within(mha).queryByRole("link")).toBeNull()
    expect(screen.queryByText(/Set the Sonarr link URL/)).toBeNull()
  })

  it("falls back to a browser-reachable Sonarr service URL", () => {
    vi.mocked(useLanguagarrStatus).mockReturnValue(
      queryResult({
        ...STATUS,
        settings: { ...SETTINGS, sonarr_link_url: "" },
      }),
    )
    vi.mocked(useServiceSettings).mockReturnValue(
      queryResult(services("http://nas.lan:8989")),
    )
    render(<Languagarr />)
    expect(
      screen.getByRole("link", { name: "Open Log Horizon in Sonarr" }),
    ).toHaveAttribute("href", "http://nas.lan:8989/series/log-horizon")
  })

  it("points a Docker-internal Sonarr URL at the host the browser used", () => {
    vi.mocked(useLanguagarrStatus).mockReturnValue(
      queryResult({
        ...STATUS,
        settings: { ...SETTINGS, sonarr_link_url: "" },
      }),
    )
    render(<Languagarr />)
    expect(
      screen.getByRole("link", { name: "Open Log Horizon in Sonarr" }),
    ).toHaveAttribute(
      "href",
      `http://${window.location.hostname}:8989/series/log-horizon`,
    )
    expect(screen.queryByText(/Set the Sonarr link URL/)).toBeNull()
  })

  it("hides the links when no Sonarr URL is known", () => {
    vi.mocked(useLanguagarrStatus).mockReturnValue(
      queryResult({
        ...STATUS,
        settings: { ...SETTINGS, sonarr_link_url: "" },
      }),
    )
    vi.mocked(useServiceSettings).mockReturnValue(
      queryResult<ServicesSettings>(undefined),
    )
    render(<Languagarr />)
    expect(screen.queryByRole("link")).toBeNull()
    expect(screen.getByText(/Set the Sonarr link URL/)).toBeInTheDocument()
  })

  it("starts a scan and shows the scanning label and errors", async () => {
    const user = userEvent.setup()
    const scan = vi.fn()
    vi.mocked(useScanLanguagarr).mockReturnValue(mutationResult(scan))
    const { rerender } = render(<Languagarr />)
    await user.click(screen.getByRole("button", { name: "Scan" }))
    expect(scan).toHaveBeenCalled()

    vi.mocked(useLanguagarrResults).mockReturnValue(
      queryResult({
        ...RESULTS,
        scan: {
          ...SCAN,
          is_scanning: true,
          last_error: "Sonarr has no quality profile named X",
        },
      }),
    )
    rerender(<Languagarr />)
    expect(screen.getByRole("button", { name: "Scanning" })).toBeDisabled()
    expect(
      screen.getByText("Sonarr has no quality profile named X"),
    ).toBeInTheDocument()
  })

  it("prompts for a first scan and handles loading and empty results", () => {
    const empty = {
      ...SCAN,
      last_scan_at: null,
      profiles_in_scope: [],
      non_compliant: 0,
    }
    vi.mocked(useLanguagarrResults).mockReturnValue(
      queryResult({ scan: empty, results: [], unknown: [] }),
    )
    const { rerender } = render(<Languagarr />)
    expect(
      screen.getByText(/Run a scan to list anime files/),
    ).toBeInTheDocument()
    expect(screen.getByText("Not scanned yet")).toBeInTheDocument()
    expect(screen.getByText(/on the Anime quality profile/)).toBeInTheDocument()

    vi.mocked(useLanguagarrResults).mockReturnValue(
      queryResult({ scan: SCAN, results: [], unknown: [] }),
    )
    rerender(<Languagarr />)
    expect(
      screen.getByText("Every scanned anime file has a English audio track."),
    ).toBeInTheDocument()

    vi.mocked(useLanguagarrResults).mockReturnValue(
      queryResult<LanguagarrResults>(undefined, true),
    )
    vi.mocked(useLanguagarrStatus).mockReturnValue(
      queryResult<LanguagarrStatus>(undefined, true),
    )
    rerender(<Languagarr />)
    expect(screen.getByText("Loading results…")).toBeInTheDocument()
    expect(
      screen.getByText(/on the configured quality profile/),
    ).toBeInTheDocument()
  })

  it("renders results without unknown files", () => {
    vi.mocked(useLanguagarrResults).mockReturnValue(
      queryResult({ ...RESULTS, unknown: [] }),
    )
    render(<Languagarr />)
    expect(screen.queryByText(/Unknown audio \(/)).not.toBeInTheDocument()
  })

  it("queues the selected files and clears the selection on success", async () => {
    const user = userEvent.setup()
    const enqueue = succeedingMutate<number[]>()
    vi.mocked(useEnqueueLanguagarr).mockReturnValue(mutationResult(enqueue))
    render(<Languagarr />)

    const queueButton = screen.getByRole("button", { name: /Queue search/ })
    expect(queueButton).toBeDisabled()
    await user.click(
      screen.getByRole("checkbox", { name: "Select Log Horizon S01E01" }),
    )
    await user.click(
      screen.getByRole("checkbox", {
        name: "Select all files in My Hero Academia",
      }),
    )
    expect(
      screen.getByRole("button", { name: "Queue search (2)" }),
    ).toBeEnabled()
    await user.click(screen.getByRole("button", { name: "Queue search (2)" }))

    expect(enqueue).toHaveBeenCalledWith([1, 3], expect.anything())
    expect(
      screen.getByRole("button", { name: "Queue search (0)" }),
    ).toBeDisabled()
  })

  it("selects everything, shows partial group state and clears again", async () => {
    const user = userEvent.setup()
    render(<Languagarr />)
    await user.click(
      screen.getByRole("checkbox", { name: "Select Log Horizon S01E02" }),
    )
    const groupBox = screen.getByRole("checkbox", {
      name: "Select all files in Log Horizon",
    }) as HTMLInputElement
    expect(groupBox.indeterminate).toBe(true)
    await user.click(
      screen.getByRole("checkbox", { name: "Select Log Horizon S01E02" }),
    )
    expect(groupBox.indeterminate).toBe(false)

    await user.click(screen.getByRole("button", { name: "Select all" }))
    expect(
      screen.getByRole("button", { name: "Queue search (3)" }),
    ).toBeEnabled()
    await user.click(screen.getByRole("button", { name: "Clear selection" }))
    expect(
      screen.getByRole("button", { name: "Queue search (0)" }),
    ).toBeDisabled()
  })

  it("deletes after confirmation and clears the selection", async () => {
    const user = userEvent.setup()
    const remove = succeedingMutate<number[]>()
    vi.mocked(useDeleteLanguagarr).mockReturnValue(mutationResult(remove))
    render(<Languagarr />)

    expect(
      screen.getByRole("button", { name: "Delete & search (0)" }),
    ).toBeDisabled()
    await user.click(
      screen.getByRole("checkbox", {
        name: "Select all files in My Hero Academia",
      }),
    )
    await user.click(
      screen.getByRole("button", { name: "Delete & search (1)" }),
    )
    const dialog = screen.getByRole("alertdialog")
    expect(
      within(dialog).getByText("My Hero Academia — S01E03 (jpn/jpn)"),
    ).toBeInTheDocument()
    expect(within(dialog).getByText(/Recycle Bin/)).toBeInTheDocument()
    await user.click(
      within(dialog).getByRole("button", { name: "Delete & search" }),
    )

    expect(remove).toHaveBeenCalledWith([3], expect.anything())
    expect(
      screen.getByRole("button", { name: "Delete & search (0)" }),
    ).toBeDisabled()
  })

  it("cancelling the delete dialog never deletes", async () => {
    const user = userEvent.setup()
    const remove = vi.fn()
    vi.mocked(useDeleteLanguagarr).mockReturnValue(mutationResult(remove))
    render(<Languagarr />)
    await user.click(
      screen.getByRole("checkbox", { name: "Select Log Horizon S01E01" }),
    )
    await user.click(
      screen.getByRole("button", { name: "Delete & search (1)" }),
    )
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    expect(remove).not.toHaveBeenCalled()
  })

  it("disables delete above the 25-file cap", async () => {
    const user = userEvent.setup()
    const many = Array.from({ length: 26 }, (_, index) => item(index + 1))
    vi.mocked(useLanguagarrResults).mockReturnValue(
      queryResult({ ...RESULTS, results: many }),
    )
    render(<Languagarr />)
    await user.click(screen.getByRole("button", { name: "Select all" }))
    const deleteButton = screen.getByRole("button", {
      name: "Delete & search (26)",
    })
    expect(deleteButton).toBeDisabled()
    expect(deleteButton).toHaveAttribute(
      "title",
      "Select at most 25 files to delete at once",
    )
  })

  it("disables Select all when only unknown-audio files remain", () => {
    vi.mocked(useLanguagarrResults).mockReturnValue(
      queryResult({ ...RESULTS, results: [], unknown: [item(7)] }),
    )
    render(<Languagarr />)
    expect(screen.getByRole("button", { name: "Select all" })).toBeDisabled()
  })

  it("disables actions while Languagarr is running", () => {
    vi.mocked(useLanguagarrStatus).mockReturnValue(
      queryResult({ ...STATUS, running: true }),
    )
    render(<Languagarr />)
    expect(screen.getByRole("button", { name: "Scan" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Select all" })).toBeDisabled()
  })

  it("collapses and expands a series", async () => {
    const user = userEvent.setup()
    render(<Languagarr />)
    await user.click(
      screen.getByRole("button", { name: "Collapse Log Horizon" }),
    )
    expect(screen.queryByText("S01E01")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Expand Log Horizon" }))
    expect(screen.getByText("S01E01")).toBeInTheDocument()
  })
})

describe("Languagarr queue", () => {
  beforeEach(() => {
    localStorage.setItem(LANGUAGARR_TAB_STORAGE_KEY, "queue")
  })

  it("lists queue rows with status, reason and errors", () => {
    render(<Languagarr />)
    expect(screen.getByText("Log Horizon - S01E02")).toBeInTheDocument()
    expect(screen.getByText("legacy_reason")).toBeInTheDocument()
    expect(screen.getByText("sonarr API request failed")).toBeInTheDocument()
    // The stat label and the failed row's status badge.
    expect(screen.getAllByText("Failed")).toHaveLength(2)
    expect(screen.getByText(/scheduled worker is off/)).toBeInTheDocument()
    // Only the row with a known series slug links to Sonarr.
    const links = screen.getAllByRole("link")
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAccessibleName("Open Log Horizon - S01E02 in Sonarr")
    expect(links[0]).toHaveAttribute(
      "href",
      "http://192.168.0.2:8989/series/log-horizon",
    )
  })

  it("describes the enabled worker", () => {
    vi.mocked(useLanguagarrStatus).mockReturnValue(
      queryResult({ ...STATUS, settings: { ...SETTINGS, enabled: true } }),
    )
    render(<Languagarr />)
    expect(
      screen.getByText(
        "The worker sends up to 10 search(es) every 60 minutes.",
      ),
    ).toBeInTheDocument()
  })

  it("runs a batch and clears pending after confirmation", async () => {
    const user = userEvent.setup()
    const runNow = vi.fn()
    const clear = vi.fn()
    vi.mocked(useRunLanguagarr).mockReturnValue(mutationResult(runNow))
    vi.mocked(useClearLanguagarrPending).mockReturnValue(mutationResult(clear))
    render(<Languagarr />)

    await user.click(screen.getByRole("button", { name: "Run a batch now" }))
    expect(runNow).toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: "Clear pending" }))
    const dialog = screen.getByRole("alertdialog")
    await user.click(
      within(dialog).getByRole("button", { name: "Clear pending" }),
    )
    expect(clear).toHaveBeenCalled()
  })

  it("shows loading and empty states and disables actions with nothing pending", () => {
    vi.mocked(useLanguagarrQueue).mockReturnValue(
      queryResult<LanguagarrQueue>(undefined, true),
    )
    const { rerender } = render(<Languagarr />)
    expect(screen.getByText("Loading queue…")).toBeInTheDocument()

    vi.mocked(useLanguagarrQueue).mockReturnValue(
      queryResult({ counts: { pending: 0, searched: 0, failed: 0 }, rows: [] }),
    )
    vi.mocked(useLanguagarrStatus).mockReturnValue(
      queryResult<LanguagarrStatus>(undefined),
    )
    rerender(<Languagarr />)
    expect(screen.getByText("The queue is empty.")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Run a batch now" }),
    ).toBeDisabled()
    expect(screen.getByRole("button", { name: "Clear pending" })).toBeDisabled()
  })
})

describe("Languagarr settings", () => {
  beforeEach(() => {
    localStorage.setItem(LANGUAGARR_TAB_STORAGE_KEY, "settings")
  })

  it("shows a loading state", () => {
    vi.mocked(useLanguagarrSettings).mockReturnValue(
      queryResult<LanguagarrSettings>(undefined, true),
    )
    render(<Languagarr />)
    expect(screen.getByText("Loading Languagarr settings…")).toBeInTheDocument()
  })

  it("saves only the changed fields", async () => {
    const user = userEvent.setup()
    const save = vi.fn()
    vi.mocked(useUpdateLanguagarrSettings).mockReturnValue(mutationResult(save))
    render(<Languagarr />)

    const saveButton = screen.getByRole("button", { name: "Save" })
    expect(saveButton).toBeDisabled()
    await user.click(
      screen.getByRole("switch", { name: "Run the scheduled search worker" }),
    )
    await user.click(
      screen.getByRole("switch", { name: "Scan and queue automatically" }),
    )
    await user.click(
      screen.getByRole("switch", {
        name: "Monitored series and episodes only",
      }),
    )
    const perRun = screen.getByLabelText("Searches per run")
    await user.clear(perRun)
    await user.type(perRun, "5")
    await user.click(screen.getByRole("checkbox", { name: "Anime 4K" }))
    const linkUrl = screen.getByLabelText("Sonarr link URL")
    await user.clear(linkUrl)
    await user.type(linkUrl, "nas.lan:8989/")
    await user.click(saveButton)

    expect(save).toHaveBeenCalledWith({
      enabled: true,
      auto_queue: true,
      monitored_only: false,
      searches_per_run: 5,
      quality_profile_names: ["Anime", "Anime 4K"],
      sonarr_link_url: "http://nas.lan:8989",
    })
  })

  it("clears the link URL and blocks unsupported schemes", async () => {
    const user = userEvent.setup()
    const save = vi.fn()
    vi.mocked(useUpdateLanguagarrSettings).mockReturnValue(mutationResult(save))
    render(<Languagarr />)
    const linkUrl = screen.getByLabelText("Sonarr link URL")
    await user.clear(linkUrl)
    await user.type(linkUrl, "ftp://nas.lan")
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled()

    await user.clear(linkUrl)
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(save).toHaveBeenCalledWith({ sonarr_link_url: "" })
  })

  it("blocks saving invalid numbers or an empty profile list", async () => {
    const user = userEvent.setup()
    render(<Languagarr />)
    const interval = screen.getByLabelText("Worker interval (minutes)")
    await user.clear(interval)
    await user.type(interval, "5")
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled()

    await user.clear(interval)
    await user.type(interval, "30")
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled()

    await user.click(screen.getByRole("checkbox", { name: "Anime" }))
    expect(screen.getByRole("checkbox", { name: "Anime" })).not.toBeChecked()
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled()
  })

  it("lists Sonarr's profiles as a checklist with the scope checked", () => {
    render(<Languagarr />)
    const group = screen.getByRole("group", {
      name: "Sonarr quality profiles in scope",
    })
    const boxes = within(group).getAllByRole("checkbox")
    expect(boxes).toHaveLength(3)
    expect(within(group).getByRole("checkbox", { name: "Anime" })).toBeChecked()
    expect(
      within(group).getByRole("checkbox", { name: "HD Bluray + WEB" }),
    ).not.toBeChecked()
  })

  it("saves a reordered but identical scope as no change", async () => {
    const user = userEvent.setup()
    vi.mocked(useLanguagarrSettings).mockReturnValue(
      queryResult({
        ...SETTINGS,
        quality_profile_names: ["Anime 4K", "Anime"],
      }),
    )
    render(<Languagarr />)
    const save = screen.getByRole("button", { name: "Save" })
    await user.click(screen.getByRole("checkbox", { name: "Anime" }))
    await user.click(screen.getByRole("checkbox", { name: "Anime" }))
    // Re-checking appends "Anime" last; the set is unchanged, so nothing to save.
    expect(save).toBeDisabled()
  })

  it("keeps a profile Sonarr no longer has visible so it can be unchecked", async () => {
    const user = userEvent.setup()
    const save = vi.fn()
    vi.mocked(useUpdateLanguagarrSettings).mockReturnValue(mutationResult(save))
    vi.mocked(useLanguagarrSettings).mockReturnValue(
      queryResult({ ...SETTINGS, quality_profile_names: ["Anime", "Old"] }),
    )
    render(<Languagarr />)
    expect(screen.getByText("(not in Sonarr)")).toBeInTheDocument()
    await user.click(screen.getByRole("checkbox", { name: /Old/ }))
    expect(screen.queryByText("(not in Sonarr)")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(save).toHaveBeenCalledWith({ quality_profile_names: ["Anime"] })
  })

  it.each([
    [
      "loading",
      queryResult<LanguagarrQualityProfile[]>(undefined, true),
      "Loading Sonarr quality profiles…",
    ],
    [
      "a load error",
      queryResult<LanguagarrQualityProfile[]>(undefined, false, {
        error: new Error("sonarr down"),
      }),
      "Could not load Sonarr quality profiles: sonarr down",
    ],
    [
      "no profiles",
      queryResult<LanguagarrQualityProfile[]>([]),
      "Sonarr reported no quality profiles.",
    ],
  ])("explains %s and still shows the saved scope", (_name, result, notice) => {
    vi.mocked(useLanguagarrProfiles).mockReturnValue(result)
    render(<Languagarr />)
    expect(screen.getByText(notice)).toBeInTheDocument()
    expect(screen.getByRole("checkbox", { name: /Anime/ })).toBeChecked()
  })

  it("hides the list when there is nothing to show", () => {
    vi.mocked(useLanguagarrProfiles).mockReturnValue(
      queryResult<LanguagarrQualityProfile[]>([]),
    )
    vi.mocked(useLanguagarrSettings).mockReturnValue(
      queryResult({ ...SETTINGS, quality_profile_names: [] }),
    )
    render(<Languagarr />)
    const group = screen.getByRole("group", {
      name: "Sonarr quality profiles in scope",
    })
    expect(within(group).queryByRole("checkbox")).not.toBeInTheDocument()
  })

  it("stops further checks at the profile limit", () => {
    const many = Array.from({ length: 21 }, (_, index) => ({
      id: index,
      name: `Profile ${String(index).padStart(2, "0")}`,
    }))
    vi.mocked(useLanguagarrProfiles).mockReturnValue(queryResult(many))
    vi.mocked(useLanguagarrSettings).mockReturnValue(
      queryResult({
        ...SETTINGS,
        quality_profile_names: many.slice(0, 20).map((profile) => profile.name),
      }),
    )
    render(<Languagarr />)
    expect(screen.getByRole("checkbox", { name: "Profile 20" })).toBeDisabled()
    expect(screen.getByRole("checkbox", { name: "Profile 00" })).toBeEnabled()
  })
})

describe("Languagarr target languages", () => {
  it("labels the review with the languages of the last scan", () => {
    vi.mocked(useLanguagarrResults).mockReturnValue(
      queryResult({
        ...RESULTS,
        scan: { ...SCAN, target_languages: ["eng", "tur"] },
      }),
    )
    render(<Languagarr />)
    expect(
      screen.getByText("Without English or Turkish audio"),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/passes when it has a English or Turkish audio track/),
    ).toBeInTheDocument()
  })

  it("uses the configured languages before the first scan", () => {
    const empty = { ...SCAN, last_scan_at: null, target_languages: [] }
    vi.mocked(useLanguagarrResults).mockReturnValue(
      queryResult({ scan: empty, results: [], unknown: [] }),
    )
    vi.mocked(useLanguagarrStatus).mockReturnValue(
      queryResult({
        ...STATUS,
        scan: empty,
        settings: { ...SETTINGS, target_audio_languages: ["tur"] },
      }),
    )
    render(<Languagarr />)
    expect(
      screen.getByText(/without a Turkish audio\s+track/),
    ).toBeInTheDocument()
  })

  it("falls back to upper-cased codes while the catalogue loads", () => {
    vi.mocked(useLanguagarrLanguages).mockReturnValue(
      queryResult<LanguagarrAudioLanguage[]>(undefined, true),
    )
    render(<Languagarr />)
    expect(screen.getByText("Without ENG audio")).toBeInTheDocument()
  })
})

describe("Languagarr language settings", () => {
  beforeEach(() => {
    localStorage.setItem(LANGUAGARR_TAB_STORAGE_KEY, "settings")
  })

  it("lists the catalogue and saves the checked languages", async () => {
    const user = userEvent.setup()
    const save = vi.fn()
    vi.mocked(useUpdateLanguagarrSettings).mockReturnValue(mutationResult(save))
    render(<Languagarr />)
    const group = screen.getByRole("group", { name: "Target audio languages" })
    expect(within(group).getAllByRole("checkbox")).toHaveLength(3)
    expect(
      within(group).getByRole("checkbox", { name: "English" }),
    ).toBeChecked()

    await user.click(within(group).getByRole("checkbox", { name: "Turkish" }))
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(save).toHaveBeenCalledWith({
      target_audio_languages: ["eng", "tur"],
    })
  })

  it("blocks saving with no language checked", async () => {
    const user = userEvent.setup()
    render(<Languagarr />)
    const group = screen.getByRole("group", { name: "Target audio languages" })
    await user.click(within(group).getByRole("checkbox", { name: "English" }))
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled()
  })

  it.each([
    [
      "loading",
      queryResult<LanguagarrAudioLanguage[]>(undefined, true),
      "Loading languages…",
    ],
    [
      "a load error",
      queryResult<LanguagarrAudioLanguage[]>(undefined, false, {
        error: new Error("offline"),
      }),
      "Could not load the language list: offline",
    ],
  ])(
    "explains %s and keeps the saved choice visible",
    (_name, result, notice) => {
      vi.mocked(useLanguagarrLanguages).mockReturnValue(result)
      render(<Languagarr />)
      expect(screen.getByText(notice)).toBeInTheDocument()
      expect(screen.getByRole("checkbox", { name: "ENG" })).toBeChecked()
    },
  )

  it("stops further checks at the language limit", () => {
    const catalogue = Array.from({ length: 11 }, (_, index) => ({
      code: `l${String(index).padStart(2, "0")}`,
      name: `Language ${String(index).padStart(2, "0")}`,
    }))
    vi.mocked(useLanguagarrLanguages).mockReturnValue(queryResult(catalogue))
    vi.mocked(useLanguagarrSettings).mockReturnValue(
      queryResult({
        ...SETTINGS,
        target_audio_languages: catalogue.slice(0, 10).map((item) => item.code),
      }),
    )
    render(<Languagarr />)
    expect(screen.getByRole("checkbox", { name: "Language 10" })).toBeDisabled()
    expect(screen.getByRole("checkbox", { name: "Language 00" })).toBeEnabled()
  })
})
