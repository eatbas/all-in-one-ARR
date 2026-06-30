import { render as rtlRender, screen, within } from "@testing-library/react"
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
}

const STATUS: DeletarrStatus = {
  settings: SETTINGS,
  libraries: {
    movies: {
      type: "movies",
      path: "/media/movies",
      last_scan_at: "2026-06-30T16:12:00Z",
      last_error: null,
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
      is_checked: true,
      videos_in_folder: [{ name: "Dune.mkv", size: 7_000_000_000 }],
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
      is_checked: true,
      videos_in_folder: [],
    },
  ],
}

const TV_RESULTS: DeletarrResults = {
  type: "tv",
  path: "/media/tv",
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
  vi.mocked(useDeleteDeletarrItems).mockReturnValue(mutationResult(vi.fn(), false))
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
      screen.getByText("Review junk files and folders in your media libraries before deleting them."),
    ).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "Dune" })).toBeInTheDocument()
    expect(screen.getByText("Protected video: Dune.mkv")).toBeInTheDocument()
    expect(screen.getByLabelText("Select movie.nfo")).toBeChecked()
    expect(screen.getByLabelText("Select sample.txt")).not.toBeChecked()
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
    expect(screen.getByText("No junk candidates found for tv shows.")).toBeInTheDocument()
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

  it("starts a scan for the active library", async () => {
    const user = userEvent.setup()
    const mutate = vi.fn()
    vi.mocked(useScanDeletarr).mockReturnValue(mutationResult(mutate, false))
    render(<Deletarr />)

    await user.click(screen.getByRole("button", { name: "Scan" }))

    expect(mutate).toHaveBeenCalledWith("movies")
  })

  it("shows the running scan label", () => {
    vi.mocked(useDeletarrStatus).mockReturnValue(
      queryResult({
        ...STATUS,
        libraries: {
          ...STATUS.libraries,
          movies: {
            ...STATUS.libraries.movies,
            stats: { ...STATUS.libraries.movies.stats, is_scanning: true },
          },
        },
      }),
    )

    render(<Deletarr />)

    expect(screen.getByRole("button", { name: "Scanning" })).toBeDisabled()
  })

  it("selects a whole group and deletes after confirmation", async () => {
    const user = userEvent.setup()
    const mutate = vi.fn()
    vi.mocked(useDeleteDeletarrItems).mockReturnValue(mutationResult(mutate, false))
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
          "/media/movies/@eaDir",
          "/media/movies/Dune/sample.txt",
        ],
      },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    )
  })

  it("unselects individual and grouped candidates", async () => {
    const user = userEvent.setup()
    render(<Deletarr />)

    await user.click(screen.getByLabelText("Select movie.nfo"))
    expect(screen.getByText("1 of 3 candidate(s) selected.")).toBeInTheDocument()

    const duneGroup = screen.getByRole("region", { name: "Dune" })
    await user.click(within(duneGroup).getByLabelText("Select group"))
    expect(screen.getByText("3 of 3 candidate(s) selected.")).toBeInTheDocument()
    await user.click(within(duneGroup).getByLabelText("Select group"))
    expect(screen.getByText("1 of 3 candidate(s) selected.")).toBeInTheDocument()
  })

  it("does not duplicate an already selected item", async () => {
    const user = userEvent.setup()
    render(<Deletarr />)

    await user.click(screen.getByLabelText("Select sample.txt"))
    await user.click(screen.getByLabelText("Select sample.txt"))

    expect(screen.getByText("2 of 3 candidate(s) selected.")).toBeInTheDocument()
  })

  it("clears local selection when delete succeeds", async () => {
    const user = userEvent.setup()
    const mutate = vi.fn((_variables, options?: { onSuccess?: () => void }) => {
      options?.onSuccess?.()
    })
    vi.mocked(useDeleteDeletarrItems).mockReturnValue(mutationResult(mutate, false))
    render(<Deletarr />)

    await user.click(screen.getByRole("button", { name: "Delete selected" }))
    await user.click(screen.getByRole("button", { name: "Delete" }))

    expect(screen.getByText("0 of 3 candidate(s) selected.")).toBeInTheDocument()
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
