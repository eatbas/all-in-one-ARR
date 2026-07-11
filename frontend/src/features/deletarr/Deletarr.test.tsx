import {
  render as rtlRender,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useDeletarrStatus: vi.fn(),
  useDeletarrResults: vi.fn(),
  useDeletarrSettings: vi.fn(),
  useUpdateDeletarrSettings: vi.fn(),
  useScanDeletarr: vi.fn(),
  useDeleteDeletarrItems: vi.fn(),
}))

import { Deletarr } from "@/features/deletarr/Deletarr"
import { DELETARR_TAB_STORAGE_KEY } from "@/features/deletarr/deletarr-tab"
import type {
  DeletarrLibraryType,
  DeletarrResults,
  DeletarrSettings,
  DeletarrStatus,
} from "@/shared/lib/api"
import {
  useDeleteDeletarrItems,
  useDeletarrResults,
  useDeletarrSettings,
  useDeletarrStatus,
  useScanDeletarr,
  useUpdateDeletarrSettings,
} from "@/shared/lib/queries"
import { mutationResult, queryResult } from "@/shared/test/mock-query"

const SETTINGS: DeletarrSettings = {
  movies_path: "/media/movies",
  tv_path: "/media/tv",
  use_arr_source: true,
}

const STATUS: DeletarrStatus = {
  settings: SETTINGS,
  libraries: {
    movies: {
      type: "movies",
      path: "/media/movies",
      last_scan_at: "2026-06-30T16:12:00Z",
      last_error: null,
      scan_mode: "heuristic",
      arr_available: false,
      arr_detail: null,
      results_count: 3,
      stats: {
        total_files: 2,
        total_folders: 1,
        total_size: 3584,
        is_scanning: false,
        scan_progress: 100,
      },
    },
    tv: {
      type: "tv",
      path: "/media/tv",
      last_scan_at: null,
      last_error: null,
      scan_mode: "heuristic",
      arr_available: false,
      arr_detail: null,
      results_count: 0,
      stats: {
        total_files: 0,
        total_folders: 0,
        total_size: 0,
        is_scanning: false,
        scan_progress: 0,
      },
    },
  },
}

const MOVIE_RESULTS: DeletarrResults = {
  type: "movies",
  path: "/media/movies",
  scan_mode: "heuristic",
  arr_available: false,
  arr_detail: null,
  stats: STATUS.libraries.movies.stats,
  results: [
    {
      path: "/media/movies/Dune/movie.nfo",
      name: "movie.nfo",
      type: "file",
      size: 1024,
      reason: "NFO metadata file",
      parent: "/media/movies/Dune",
      movie_folder: "Dune",
      movie_folder_path: "/media/movies/Dune",
      is_checked: false,
      videos_in_folder: [{ name: "Dune.mkv", size: 7_000_000_000 }],
      origin: "heuristic",
      category: "junk",
    },
    {
      path: "/media/movies/Dune/sample.txt",
      name: "sample.txt",
      type: "file",
      size: 512,
      reason: "Junk sidecar file",
      parent: "/media/movies/Dune",
      movie_folder: "Dune",
      movie_folder_path: "/media/movies/Dune",
      is_checked: false,
      videos_in_folder: [{ name: "Dune.mkv", size: 7_000_000_000 }],
      origin: "heuristic",
      category: "junk",
    },
    {
      path: "/media/movies/@eaDir",
      name: "@eaDir",
      type: "folder",
      size: 2048,
      reason: "Known junk folder",
      parent: "/media/movies",
      movie_folder: null,
      movie_folder_path: null,
      is_checked: false,
      videos_in_folder: [],
      origin: "heuristic",
      category: "junk",
    },
  ],
}

const TV_RESULTS: DeletarrResults = {
  type: "tv",
  path: "/media/tv",
  scan_mode: "heuristic",
  arr_available: false,
  arr_detail: null,
  stats: STATUS.libraries.tv.stats,
  results: [],
}

const DELAYED_VIDEO_RESULTS: DeletarrResults = {
  ...MOVIE_RESULTS,
  results: [
    {
      ...MOVIE_RESULTS.results[0],
      videos_in_folder: [],
    },
    {
      ...MOVIE_RESULTS.results[1],
      videos_in_folder: [{ name: "Dune.mkv", size: 7_000_000_000 }],
    },
  ],
}

const MIXED_RESULTS: DeletarrResults = {
  ...MOVIE_RESULTS,
  results: [
    ...MOVIE_RESULTS.results,
    {
      path: "/media/movies/Unknown Thing",
      name: "Unknown Thing",
      type: "folder",
      size: 4096,
      reason: "Orphaned folder (not in Radarr)",
      parent: "/media/movies",
      movie_folder: "Unknown Thing",
      movie_folder_path: "/media/movies/Unknown Thing",
      is_checked: false,
      videos_in_folder: [],
      origin: "arr",
      category: "untracked_media",
    },
  ],
}

const ARR_RESULTS_WITH_EMPTY_FOLDER: DeletarrResults = {
  ...MOVIE_RESULTS,
  scan_mode: "arr",
  arr_available: true,
  results: [
    ...MOVIE_RESULTS.results,
    {
      path: "/media/movies/Empty Film",
      name: "Empty Film",
      type: "folder",
      size: 0,
      reason: "Empty folder",
      parent: "/media/movies",
      movie_folder: "Empty Film",
      movie_folder_path: "/media/movies/Empty Film",
      is_checked: false,
      videos_in_folder: [],
      origin: "arr",
      category: "junk",
    },
  ],
}

function resultsFor(type: DeletarrLibraryType) {
  return type === "movies" ? MOVIE_RESULTS : TV_RESULTS
}

function render(ui: ReactElement) {
  return rtlRender(ui)
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(useDeletarrStatus).mockReturnValue(queryResult(STATUS))
  vi.mocked(useDeletarrResults).mockImplementation((type) =>
    queryResult(resultsFor(type)),
  )
  vi.mocked(useDeletarrSettings).mockReturnValue(queryResult(SETTINGS))
  vi.mocked(useUpdateDeletarrSettings).mockReturnValue(
    mutationResult(vi.fn(), false),
  )
  vi.mocked(useScanDeletarr).mockReturnValue(mutationResult(vi.fn(), false))
  vi.mocked(useDeleteDeletarrItems).mockReturnValue(
    mutationResult(vi.fn(), false),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("Deletarr", () => {
  it("defaults to Movies and renders grouped scan results", () => {
    render(<Deletarr />)

    expect(screen.getByRole("tab", { name: "Movies" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(
      screen.getByText(
        "Review junk files, empty folders, and untracked media in your libraries before deleting them.",
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "Dune" })).toBeInTheDocument()
    expect(screen.getByText("Protected video: Dune.mkv")).toBeInTheDocument()
    expect(
      screen.getByText("0 of 3 candidate(s) selected."),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Delete selected" }),
    ).toBeDisabled()
    expect(screen.getByLabelText("Select movie.nfo")).not.toBeChecked()
    expect(screen.getByLabelText("Select sample.txt")).not.toBeChecked()
    expect(screen.getByLabelText("Select all junk")).not.toBeChecked()
  })

  it("prompts a re-scan when the source of truth is on but results are heuristic", () => {
    vi.mocked(useDeletarrStatus).mockReturnValue(
      queryResult({
        ...STATUS,
        libraries: {
          ...STATUS.libraries,
          movies: {
            ...STATUS.libraries.movies,
            arr_detail: "Arr source disabled",
          },
        },
      }),
    )
    render(<Deletarr />)

    expect(
      screen.getByText(
        "Heuristic results. Re-scan to verify candidates against Radarr library metadata.",
      ),
    ).toBeInTheDocument()
    // An enabled toggle must never surface the disabled-source notice.
    expect(screen.queryByText(/Arr source disabled/)).not.toBeInTheDocument()
  })

  it("labels the enabled re-scan prompt with Sonarr on the TV tab", async () => {
    const user = userEvent.setup()
    render(<Deletarr />)

    await user.click(screen.getByRole("tab", { name: "TV Shows" }))

    expect(
      screen.getByText(
        "Heuristic results. Re-scan to verify candidates against Sonarr library metadata.",
      ),
    ).toBeInTheDocument()
  })

  it("shows the disabled-source notice only when the toggle is off", () => {
    vi.mocked(useDeletarrStatus).mockReturnValue(
      queryResult({
        ...STATUS,
        settings: { ...SETTINGS, use_arr_source: false },
        libraries: {
          ...STATUS.libraries,
          movies: {
            ...STATUS.libraries.movies,
            arr_detail: "Arr source disabled",
          },
        },
      }),
    )

    render(<Deletarr />)

    expect(screen.getByText(/Arr source disabled/)).toBeInTheDocument()
    expect(
      screen.getByText(/Turn on the source-of-truth setting/),
    ).toBeInTheDocument()
  })

  it("explains how to enable Arr when no disabled-source detail is supplied", () => {
    vi.mocked(useDeletarrStatus).mockReturnValue(
      queryResult({
        ...STATUS,
        settings: { ...SETTINGS, use_arr_source: false },
      }),
    )

    render(<Deletarr />)

    expect(
      screen.getByText(/Heuristic scan\. Turn on the source-of-truth setting/),
    ).toBeInTheDocument()
  })

  it("shows why the heuristic fallback was used when Arr is unreachable", () => {
    vi.mocked(useDeletarrStatus).mockReturnValue(
      queryResult({
        ...STATUS,
        libraries: {
          ...STATUS.libraries,
          movies: {
            ...STATUS.libraries.movies,
            arr_detail: "radarr connection is not configured",
          },
        },
      }),
    )

    render(<Deletarr />)

    expect(
      screen.getByText(/radarr connection is not configured/),
    ).toBeInTheDocument()
  })

  it("describes Arr verification without excluding known empty folders", () => {
    vi.mocked(useDeletarrResults).mockImplementation((type) =>
      queryResult(
        type === "movies" ? ARR_RESULTS_WITH_EMPTY_FOLDER : TV_RESULTS,
      ),
    )

    render(<Deletarr />)

    expect(
      screen.getByText(
        "Candidates were checked against Radarr library metadata.",
      ),
    ).toBeInTheDocument()
    expect(screen.getByText("Empty folder")).toBeInTheDocument()
    expect(screen.getByLabelText("Select Empty Film")).not.toBeChecked()
  })

  it("shows a separate group for orphaned folders not in the library", () => {
    vi.mocked(useDeletarrResults).mockImplementation((type) =>
      queryResult(
        type === "movies"
          ? {
              ...MOVIE_RESULTS,
              scan_mode: "arr",
              arr_available: true,
              results: [
                ...MOVIE_RESULTS.results,
                {
                  path: "/media/movies/Unknown Thing",
                  name: "Unknown Thing",
                  type: "folder",
                  size: 4096,
                  reason: "Orphaned folder (not in Radarr)",
                  parent: "/media/movies",
                  movie_folder: "Unknown Thing",
                  movie_folder_path: "/media/movies/Unknown Thing",
                  is_checked: false,
                  videos_in_folder: [],
                  origin: "arr",
                  category: "untracked_media",
                },
              ],
            }
          : TV_RESULTS,
      ),
    )

    render(<Deletarr />)

    expect(
      screen.getByRole("region", { name: "Untracked media" }),
    ).toBeInTheDocument()
    expect(
      screen.getByLabelText("Select all untracked media"),
    ).not.toBeChecked()
    expect(
      screen.getByRole("region", { name: "Unknown Thing" }),
    ).toBeInTheDocument()
    // The managed Dune group is still rendered separately.
    expect(screen.getByRole("region", { name: "Dune" })).toBeInTheDocument()
  })

  it("renders an untracked-only result set without an empty junk section", () => {
    vi.mocked(useDeletarrResults).mockImplementation((type) =>
      queryResult(
        type === "movies"
          ? {
              ...MIXED_RESULTS,
              results: MIXED_RESULTS.results.filter(
                (item) => item.category === "untracked_media",
              ),
            }
          : TV_RESULTS,
      ),
    )

    render(<Deletarr />)

    expect(
      screen.queryByRole("region", { name: "Junk files and folders" }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole("region", { name: "Untracked media" }),
    ).toBeInTheDocument()
  })

  it("switches to TV Shows and persists the selected tab", async () => {
    const user = userEvent.setup()
    render(<Deletarr />)

    await user.click(screen.getByRole("tab", { name: "TV Shows" }))

    expect(localStorage.getItem(DELETARR_TAB_STORAGE_KEY)).toBe("tv")
    expect(screen.getByRole("tab", { name: "TV Shows" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(
      screen.getByText("No review candidates found for tv shows."),
    ).toBeInTheDocument()
  })

  it("switches to Settings and persists the selected tab", async () => {
    const user = userEvent.setup()
    render(<Deletarr />)

    await user.click(screen.getByRole("tab", { name: "Settings" }))

    expect(localStorage.getItem(DELETARR_TAB_STORAGE_KEY)).toBe("settings")
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(screen.getByText("Media library paths")).toBeInTheDocument()
  })

  it("restores a valid stored tab and ignores invalid storage", () => {
    localStorage.setItem(DELETARR_TAB_STORAGE_KEY, "tv")
    const first = render(<Deletarr />)
    expect(screen.getByRole("tab", { name: "TV Shows" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    first.unmount()

    localStorage.setItem(DELETARR_TAB_STORAGE_KEY, "settings")
    const second = render(<Deletarr />)
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    second.unmount()

    localStorage.setItem(DELETARR_TAB_STORAGE_KEY, "bad")
    render(<Deletarr />)
    expect(screen.getByRole("tab", { name: "Movies" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
  })

  it("clears selection and starts a scan for the active library", async () => {
    const user = userEvent.setup()
    const mutate = vi.fn()
    vi.mocked(useScanDeletarr).mockReturnValue(mutationResult(mutate, false))
    render(<Deletarr />)

    await user.click(screen.getByLabelText("Select movie.nfo"))
    await user.click(screen.getByRole("button", { name: "Scan" }))

    expect(mutate).toHaveBeenCalledWith("movies")
    expect(
      screen.getByText("0 of 3 candidate(s) selected."),
    ).toBeInTheDocument()
  })

  it("shows the running scan label and clears selection on scan transition", async () => {
    const user = userEvent.setup()
    let currentStatus = STATUS
    vi.mocked(useDeletarrStatus).mockImplementation(() =>
      queryResult(currentStatus),
    )
    const view = render(<Deletarr />)
    await user.click(screen.getByLabelText("Select movie.nfo"))

    currentStatus = {
      ...STATUS,
      libraries: {
        ...STATUS.libraries,
        movies: {
          ...STATUS.libraries.movies,
          stats: { ...STATUS.libraries.movies.stats, is_scanning: true },
        },
      },
    }
    view.rerender(<Deletarr />)

    expect(screen.getByRole("button", { name: "Scanning" })).toBeDisabled()
    expect(screen.getByLabelText("Select movie.nfo")).not.toBeChecked()
  })

  it("selects a whole group and deletes after confirmation", async () => {
    const user = userEvent.setup()
    const mutate = vi.fn()
    vi.mocked(useDeleteDeletarrItems).mockReturnValue(
      mutationResult(mutate, false),
    )
    render(<Deletarr />)

    const duneGroup = screen.getByRole("region", { name: "Dune" })
    await user.click(within(duneGroup).getByLabelText("Select group"))
    await user.click(screen.getByRole("button", { name: "Delete selected" }))
    await user.click(screen.getByRole("button", { name: "Delete" }))

    expect(mutate).toHaveBeenCalledWith(
      {
        type: "movies",
        paths: [
          "/media/movies/Dune/movie.nfo",
          "/media/movies/Dune/sample.txt",
        ],
      },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    )
  })

  it("combines individual and grouped selection without affecting other groups", async () => {
    const user = userEvent.setup()
    render(<Deletarr />)

    await user.click(screen.getByLabelText("Select movie.nfo"))
    expect(
      screen.getByText("1 of 3 candidate(s) selected."),
    ).toBeInTheDocument()

    const duneGroup = screen.getByRole("region", { name: "Dune" })
    await user.click(within(duneGroup).getByLabelText("Select group"))
    expect(
      screen.getByText("2 of 3 candidate(s) selected."),
    ).toBeInTheDocument()
    await user.click(within(duneGroup).getByLabelText("Select group"))
    expect(
      screen.getByText("0 of 3 candidate(s) selected."),
    ).toBeInTheDocument()
  })

  it("does not duplicate an already selected item", async () => {
    const user = userEvent.setup()
    render(<Deletarr />)

    await user.click(screen.getByLabelText("Select sample.txt"))
    const duneGroup = screen.getByRole("region", { name: "Dune" })
    await user.click(within(duneGroup).getByLabelText("Select group"))

    expect(
      screen.getByText("2 of 3 candidate(s) selected."),
    ).toBeInTheDocument()
  })

  it("selects and clears junk and untracked media independently", async () => {
    const user = userEvent.setup()
    vi.mocked(useDeletarrResults).mockImplementation((type) =>
      queryResult(type === "movies" ? MIXED_RESULTS : TV_RESULTS),
    )
    render(<Deletarr />)

    const junkSelector = screen.getByLabelText("Select all junk")
    const untrackedSelector = screen.getByLabelText(
      "Select all untracked media",
    )
    await user.click(junkSelector)

    expect(junkSelector).toBeChecked()
    expect(untrackedSelector).not.toBeChecked()
    expect(
      screen.getByText("3 of 4 candidate(s) selected."),
    ).toBeInTheDocument()

    await user.click(screen.getByLabelText("Select movie.nfo"))
    expect(junkSelector).toBePartiallyChecked()

    await user.click(untrackedSelector)
    expect(untrackedSelector).toBeChecked()
    expect(
      screen.getByText("3 of 4 candidate(s) selected."),
    ).toBeInTheDocument()

    await user.click(junkSelector)
    expect(
      screen.getByText("4 of 4 candidate(s) selected."),
    ).toBeInTheDocument()
    await user.click(junkSelector)
    expect(
      screen.getByText("1 of 4 candidate(s) selected."),
    ).toBeInTheDocument()
    expect(screen.getByLabelText("Select Unknown Thing")).toBeChecked()
  })

  it("preserves equivalent polling selection but never restores A after A to B to A", async () => {
    const user = userEvent.setup()
    let currentResults = MOVIE_RESULTS
    vi.mocked(useDeletarrResults).mockImplementation((type) =>
      queryResult(type === "movies" ? currentResults : TV_RESULTS),
    )
    const view = render(<Deletarr />)

    await user.click(screen.getByLabelText("Select sample.txt"))
    currentResults = {
      ...MOVIE_RESULTS,
      results: [...MOVIE_RESULTS.results].reverse(),
    }
    view.rerender(<Deletarr />)
    expect(screen.getByLabelText("Select sample.txt")).toBeChecked()

    currentResults = MIXED_RESULTS
    view.rerender(<Deletarr />)
    expect(
      screen.getByText("0 of 4 candidate(s) selected."),
    ).toBeInTheDocument()

    currentResults = MOVIE_RESULTS
    view.rerender(<Deletarr />)
    expect(screen.getByLabelText("Select sample.txt")).not.toBeChecked()
    expect(
      screen.getByRole("button", { name: "Delete selected" }),
    ).toBeDisabled()
  })

  it("submits the explicit union selected from both result sections", async () => {
    const user = userEvent.setup()
    const mutate = vi.fn()
    vi.mocked(useDeletarrResults).mockImplementation((type) =>
      queryResult(type === "movies" ? MIXED_RESULTS : TV_RESULTS),
    )
    vi.mocked(useDeleteDeletarrItems).mockReturnValue(
      mutationResult(mutate, false),
    )
    render(<Deletarr />)

    await user.click(screen.getByLabelText("Select all junk"))
    await user.click(screen.getByLabelText("Select all untracked media"))
    await user.click(screen.getByRole("button", { name: "Delete selected" }))
    await user.click(screen.getByRole("button", { name: "Delete" }))

    expect(mutate).toHaveBeenCalledWith(
      {
        type: "movies",
        paths: [
          "/media/movies/Dune/movie.nfo",
          "/media/movies/Dune/sample.txt",
          "/media/movies/@eaDir",
          "/media/movies/Unknown Thing",
        ],
      },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    )
  })

  it("collapses groups independently without coupling disclosure and selection", async () => {
    const user = userEvent.setup()
    render(<Deletarr />)

    const duneGroup = screen.getByRole("region", { name: "Dune" })
    const rootGroup = screen.getByRole("region", { name: "/media/movies" })
    const collapseDune = within(duneGroup).getByRole("button", {
      name: "Collapse Dune",
    })
    expect(collapseDune).toHaveAttribute("aria-expanded", "true")

    await user.click(collapseDune)
    expect(screen.queryByLabelText("Select movie.nfo")).not.toBeInTheDocument()
    expect(
      within(rootGroup).getByLabelText("Select @eaDir"),
    ).toBeInTheDocument()

    const expandDune = within(duneGroup).getByRole("button", {
      name: "Expand Dune",
    })
    expandDune.focus()
    await user.keyboard("{Enter}")
    expect(screen.getByLabelText("Select movie.nfo")).toBeInTheDocument()

    await user.click(within(duneGroup).getByLabelText("Select group"))
    expect(
      within(duneGroup).getByRole("button", { name: "Collapse Dune" }),
    ).toHaveAttribute("aria-expanded", "true")
  })

  it("clears local selection when delete succeeds", async () => {
    const user = userEvent.setup()
    const mutate = vi.fn((_variables, options?: { onSuccess?: () => void }) => {
      options?.onSuccess?.()
    })
    vi.mocked(useDeleteDeletarrItems).mockReturnValue(
      mutationResult(mutate, false),
    )
    render(<Deletarr />)

    await user.click(screen.getByLabelText("Select movie.nfo"))
    await user.click(screen.getByRole("button", { name: "Delete selected" }))
    await user.click(screen.getByRole("button", { name: "Delete" }))

    expect(
      screen.getByText("0 of 3 candidate(s) selected."),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByLabelText("Select movie.nfo")).not.toBeChecked(),
    )
  })

  it("uses later group items for protected video context", () => {
    vi.mocked(useDeletarrResults).mockImplementation((type) =>
      queryResult(type === "movies" ? DELAYED_VIDEO_RESULTS : TV_RESULTS),
    )

    render(<Deletarr />)

    expect(screen.getByText("Protected video: Dune.mkv")).toBeInTheDocument()
  })

  it("shows unset defaults before Deletarr data is available", () => {
    vi.mocked(useDeletarrStatus).mockReturnValue(
      queryResult<DeletarrStatus>(undefined),
    )
    vi.mocked(useDeletarrResults).mockReturnValue(
      queryResult<DeletarrResults>(undefined),
    )

    render(<Deletarr />)

    expect(screen.getByText("Current path:")).toBeInTheDocument()
    expect(screen.getByText("Not set")).toBeInTheDocument()
    expect(screen.getByText("Not scanned yet")).toBeInTheDocument()
  })

  it("shows loading and backend error states", () => {
    vi.mocked(useDeletarrStatus).mockReturnValue(
      queryResult({
        ...STATUS,
        libraries: {
          ...STATUS.libraries,
          movies: {
            ...STATUS.libraries.movies,
            last_error: "Path is unavailable",
          },
        },
      }),
    )
    vi.mocked(useDeletarrResults).mockReturnValue(
      queryResult<DeletarrResults>(undefined, true),
    )

    render(<Deletarr />)

    expect(screen.getByText("Path is unavailable")).toBeInTheDocument()
    expect(screen.getByText("Loading Deletarr results...")).toBeInTheDocument()
  })

  it("survives missing localStorage", async () => {
    vi.stubGlobal("localStorage", undefined)
    const user = userEvent.setup()
    render(<Deletarr />)

    await user.click(screen.getByRole("tab", { name: "TV Shows" }))

    expect(screen.getByRole("tab", { name: "TV Shows" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
  })
})
