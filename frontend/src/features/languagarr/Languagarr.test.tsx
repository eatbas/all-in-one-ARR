import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useLanguagarrStatus: vi.fn(),
  useLanguagarrResults: vi.fn(),
  useLanguagarrSettings: vi.fn(),
  useLanguagarrQueue: vi.fn(),
  useScanLanguagarr: vi.fn(),
  useEnqueueLanguagarr: vi.fn(),
  useDeleteLanguagarr: vi.fn(),
  useRunLanguagarr: vi.fn(),
  useClearLanguagarrPending: vi.fn(),
  useUpdateLanguagarrSettings: vi.fn(),
}))

import { Languagarr } from "@/features/languagarr/Languagarr"
import { LANGUAGARR_TAB_STORAGE_KEY } from "@/features/languagarr/languagarr-tab"
import type {
  LanguagarrItem,
  LanguagarrQueue,
  LanguagarrResults,
  LanguagarrScanSummary,
  LanguagarrSettings,
  LanguagarrStatus,
} from "@/shared/lib/api"
import {
  useClearLanguagarrPending,
  useDeleteLanguagarr,
  useEnqueueLanguagarr,
  useLanguagarrQueue,
  useLanguagarrResults,
  useLanguagarrSettings,
  useLanguagarrStatus,
  useRunLanguagarr,
  useScanLanguagarr,
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
}

const SCAN: LanguagarrScanSummary = {
  is_scanning: false,
  last_scan_at: "2026-10-12T18:00:00Z",
  last_error: null,
  profiles_in_scope: ["Anime"],
  series_scanned: 2,
  files_scanned: 10,
  non_compliant: 3,
  unknown: 1,
  missing_english: 2,
  single_language: 1,
}

function item(
  id: number,
  overrides: Partial<LanguagarrItem> = {},
): LanguagarrItem {
  return {
    episode_file_id: id,
    series_id: 1,
    series_title: "Log Horizon",
    season_number: 1,
    episode_ids: [id * 10],
    episode_label: `S01E${String(id).padStart(2, "0")}`,
    relative_path: `Season 01/file-${id}.mkv`,
    audio_languages: "jpn/por",
    sonarr_languages: ["Japanese", "Portuguese"],
    verdict: "missing_english",
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
      audio_languages: "jpn/jpn",
      verdict: "missing_english",
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
      title: "Log Horizon - S01E02",
      episode_ids: [20],
      reason: "missing_english",
      status: "pending",
      queued_at: "2026-10-12T18:00:00Z",
      searched_at: null,
      attempts: 0,
      last_error: null,
    },
    {
      episode_file_id: 4,
      series_id: 1,
      title: "Log Horizon - S01E04",
      episode_ids: [40],
      reason: "single_language",
      status: "searched",
      queued_at: "2026-10-12T17:00:00Z",
      searched_at: "2026-10-12T17:30:00Z",
      attempts: 1,
      last_error: null,
    },
    {
      episode_file_id: 5,
      series_id: 1,
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
  vi.mocked(useScanLanguagarr).mockReturnValue(mutationResult(vi.fn()))
  vi.mocked(useEnqueueLanguagarr).mockReturnValue(mutationResult(vi.fn()))
  vi.mocked(useDeleteLanguagarr).mockReturnValue(mutationResult(vi.fn()))
  vi.mocked(useRunLanguagarr).mockReturnValue(mutationResult(vi.fn()))
  vi.mocked(useClearLanguagarrPending).mockReturnValue(mutationResult(vi.fn()))
  vi.mocked(useUpdateLanguagarrSettings).mockReturnValue(
    mutationResult(vi.fn()),
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
    expect(screen.getByText("Without English dual")).toBeInTheDocument()
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
      screen.getByText("Every scanned anime file has English dual audio."),
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

  it("marks files without searchable episodes as not actionable", async () => {
    const user = userEvent.setup()
    vi.mocked(useLanguagarrResults).mockReturnValue(
      queryResult({
        ...RESULTS,
        results: [
          item(1),
          item(7, { series_id: 3, series_title: "Frozen", episode_ids: [] }),
        ],
      }),
    )
    render(<Languagarr />)

    const frozen = screen.getByRole("region", { name: "Frozen" })
    expect(
      within(frozen).getByText("Not searchable (unmonitored)"),
    ).toBeInTheDocument()
    expect(
      within(frozen).getByRole("checkbox", { name: "Select Frozen S01E07" }),
    ).toBeDisabled()
    expect(
      within(frozen).getByRole("checkbox", {
        name: "Select all files in Frozen",
      }),
    ).toBeDisabled()

    // Select all only takes actionable files and reports them all selected.
    await user.click(screen.getByRole("button", { name: "Select all" }))
    expect(
      screen.getByRole("button", { name: "Queue search (1)" }),
    ).toBeEnabled()
    expect(
      screen.getByRole("button", { name: "Clear selection" }),
    ).toBeInTheDocument()
  })

  it("disables Select all when nothing is actionable", () => {
    vi.mocked(useLanguagarrResults).mockReturnValue(
      queryResult({ ...RESULTS, results: [item(7, { episode_ids: [] })] }),
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
    expect(screen.getByText("English only")).toBeInTheDocument()
    expect(screen.getByText("legacy_reason")).toBeInTheDocument()
    expect(screen.getByText("sonarr API request failed")).toBeInTheDocument()
    // The stat label and the failed row's status badge.
    expect(screen.getAllByText("Failed")).toHaveLength(2)
    expect(screen.getByText(/scheduled worker is off/)).toBeInTheDocument()
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
    const profiles = screen.getByLabelText("Sonarr quality profiles in scope")
    await user.clear(profiles)
    await user.type(profiles, "Anime, Anime 4K,")
    await user.click(saveButton)

    expect(save).toHaveBeenCalledWith({
      enabled: true,
      auto_queue: true,
      monitored_only: false,
      searches_per_run: 5,
      quality_profile_names: ["Anime", "Anime 4K"],
    })
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

    const profiles = screen.getByLabelText("Sonarr quality profiles in scope")
    await user.clear(profiles)
    await user.type(profiles, " , ")
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled()
  })
})
