import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/api", () => ({
  getDeletarrStatus: vi.fn(),
  getDeletarrSettings: vi.fn(),
  getDeletarrResults: vi.fn(),
  updateDeletarrSettings: vi.fn(),
  scanDeletarr: vi.fn(),
  deleteDeletarrItems: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import * as api from "@/shared/lib/api"
import type { DeletarrResults, DeletarrStatus } from "@/shared/lib/api"
import { toast } from "sonner"
import {
  queryKeys,
  useDeleteDeletarrItems,
  useDeletarrResults,
  useDeletarrSettings,
  useDeletarrStatus,
  useScanDeletarr,
  useUpdateDeletarrSettings,
} from "@/shared/lib/queries"
import { setup } from "@/shared/test/query-provider"

const stats = {
  total_files: 0,
  total_folders: 0,
  total_size: 0,
  is_scanning: false,
  scan_progress: 0,
}

const status: DeletarrStatus = {
  settings: {
    movies_path: "/media/movies",
    tv_path: "/media/tv",
    use_arr_source: true,
  },
  libraries: {
    movies: {
      type: "movies",
      path: "/media/movies",
      last_scan_at: null,
      last_error: null,
      scan_mode: "heuristic",
      arr_available: false,
      arr_detail: null,
      results_count: 0,
      stats,
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
      stats,
    },
  },
}

const results: DeletarrResults = {
  type: "movies",
  path: "/media/movies",
  scan_mode: "heuristic",
  arr_available: false,
  arr_detail: null,
  results: [],
  stats,
}

beforeEach(() => {
  vi.mocked(api.getDeletarrStatus).mockResolvedValue(status)
  vi.mocked(api.getDeletarrSettings).mockResolvedValue(status.settings)
  vi.mocked(api.getDeletarrResults).mockResolvedValue(results)
})

describe("Deletarr query hooks", () => {
  it("fetches status, settings, and library results", async () => {
    const { wrapper } = setup()
    const statusHook = renderHook(() => useDeletarrStatus(), { wrapper })
    const settingsHook = renderHook(() => useDeletarrSettings(), { wrapper })
    const resultsHook = renderHook(() => useDeletarrResults("movies"), {
      wrapper,
    })

    await waitFor(() => expect(statusHook.result.current.isSuccess).toBe(true))
    await waitFor(() =>
      expect(settingsHook.result.current.isSuccess).toBe(true),
    )
    await waitFor(() => expect(resultsHook.result.current.isSuccess).toBe(true))
    expect(api.getDeletarrStatus).toHaveBeenCalled()
    expect(api.getDeletarrSettings).toHaveBeenCalled()
    expect(api.getDeletarrResults).toHaveBeenCalledWith("movies")
  })

  it("invalidates Deletarr queries after settings, scan, and delete mutations", async () => {
    vi.mocked(api.updateDeletarrSettings).mockResolvedValue(status)
    vi.mocked(api.scanDeletarr).mockResolvedValue(results)
    vi.mocked(api.deleteDeletarrItems).mockResolvedValue({
      success: true,
      deleted: 1,
      failed: 0,
      freed_bytes: 1024,
      freed_mb: 0.001,
      freed_formatted: "1.0 KB",
      deleted_paths: ["/media/movies/Dune/movie.nfo"],
      errors: [],
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")

    const updateHook = renderHook(() => useUpdateDeletarrSettings(), {
      wrapper,
    })
    act(() => updateHook.result.current.mutate({ movies_path: "/srv/movies" }))
    await waitFor(() => expect(updateHook.result.current.isSuccess).toBe(true))

    const scanHook = renderHook(() => useScanDeletarr(), { wrapper })
    act(() => scanHook.result.current.mutate("movies"))
    await waitFor(() => expect(scanHook.result.current.isSuccess).toBe(true))

    const deleteHook = renderHook(() => useDeleteDeletarrItems(), { wrapper })
    act(() =>
      deleteHook.result.current.mutate({
        type: "movies",
        paths: ["/media/movies/Dune/movie.nfo"],
      }),
    )
    await waitFor(() => expect(deleteHook.result.current.isSuccess).toBe(true))

    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.deletarrStatus,
    })
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.deletarrSettings,
    })
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.deletarrResults("movies"),
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("toasts failed delete outcomes and mutation errors", async () => {
    vi.mocked(api.deleteDeletarrItems).mockResolvedValue({
      success: false,
      deleted: 1,
      failed: 1,
      freed_bytes: 1024,
      freed_mb: 0.001,
      freed_formatted: "1.0 KB",
      deleted_paths: ["/media/movies/Dune/movie.nfo"],
      errors: [{ path: "/media/movies/Dune/bad.nfo", error: "missing" }],
    })
    vi.mocked(api.updateDeletarrSettings).mockRejectedValue(
      new Error("save boom"),
    )
    vi.mocked(api.scanDeletarr).mockRejectedValue(new Error("scan boom"))
    const { wrapper } = setup()

    const deleteHook = renderHook(() => useDeleteDeletarrItems(), { wrapper })
    act(() =>
      deleteHook.result.current.mutate({
        type: "movies",
        paths: ["/media/movies/Dune/movie.nfo", "/media/movies/Dune/bad.nfo"],
      }),
    )
    await waitFor(() => expect(deleteHook.result.current.isSuccess).toBe(true))

    const updateHook = renderHook(() => useUpdateDeletarrSettings(), {
      wrapper,
    })
    act(() => updateHook.result.current.mutate({ movies_path: "/srv/movies" }))
    await waitFor(() => expect(updateHook.result.current.isError).toBe(true))

    const scanHook = renderHook(() => useScanDeletarr(), { wrapper })
    act(() => scanHook.result.current.mutate("movies"))
    await waitFor(() => expect(scanHook.result.current.isError).toBe(true))

    expect(toast.error).toHaveBeenCalledWith(
      "Some Deletarr items could not be deleted",
      { description: "1 deleted, 1 failed." },
    )
    expect(toast.error).toHaveBeenCalledWith(
      "Could not save Deletarr settings",
      {
        description: "save boom",
      },
    )
    expect(toast.error).toHaveBeenCalledWith("Could not scan library", {
      description: "scan boom",
    })
  })

  it("toasts delete mutation errors", async () => {
    vi.mocked(api.deleteDeletarrItems).mockRejectedValue(
      new Error("delete boom"),
    )
    const { wrapper } = setup()

    const deleteHook = renderHook(() => useDeleteDeletarrItems(), { wrapper })
    act(() =>
      deleteHook.result.current.mutate({
        type: "movies",
        paths: ["/media/movies/Dune/movie.nfo"],
      }),
    )
    await waitFor(() => expect(deleteHook.result.current.isError).toBe(true))

    expect(toast.error).toHaveBeenCalledWith(
      "Could not delete selected items",
      {
        description: "delete boom",
      },
    )
  })
})
