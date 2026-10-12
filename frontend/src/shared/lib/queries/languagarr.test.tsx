import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/api", () => ({
  getLanguagarrStatus: vi.fn(),
  getLanguagarrSettings: vi.fn(),
  getLanguagarrResults: vi.fn(),
  getLanguagarrQueue: vi.fn(),
  updateLanguagarrSettings: vi.fn(),
  scanLanguagarr: vi.fn(),
  enqueueLanguagarr: vi.fn(),
  deleteLanguagarr: vi.fn(),
  runLanguagarr: vi.fn(),
  clearLanguagarrPending: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import * as api from "@/shared/lib/api"
import type { LanguagarrResults, LanguagarrStatus } from "@/shared/lib/api"
import { toast } from "sonner"
import { queryKeys } from "@/shared/lib/queries/keys"
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
} from "@/shared/lib/queries/languagarr"
import { setup } from "@/shared/test/query-provider"

const SCAN = {
  is_scanning: false,
  last_scan_at: "2026-10-12T18:00:00Z",
  last_error: null,
  profiles_in_scope: ["Anime"],
  series_scanned: 1,
  files_scanned: 2,
  non_compliant: 4,
  unknown: 0,
  missing_english: 4,
}
const RESULTS: LanguagarrResults = { scan: SCAN, results: [], unknown: [] }
const STATUS = { running: false } as unknown as LanguagarrStatus

beforeEach(() => {
  vi.mocked(api.getLanguagarrStatus).mockResolvedValue(STATUS)
  vi.mocked(api.getLanguagarrSettings).mockResolvedValue(
    {} as Awaited<ReturnType<typeof api.getLanguagarrSettings>>,
  )
  vi.mocked(api.getLanguagarrResults).mockResolvedValue(RESULTS)
  vi.mocked(api.getLanguagarrQueue).mockResolvedValue({
    counts: { pending: 0, searched: 0, failed: 0 },
    rows: [],
  })
})

describe("Languagarr queries", () => {
  it.each([
    ["status", useLanguagarrStatus, api.getLanguagarrStatus],
    ["settings", useLanguagarrSettings, api.getLanguagarrSettings],
    ["results", useLanguagarrResults, api.getLanguagarrResults],
    ["queue", useLanguagarrQueue, api.getLanguagarrQueue],
  ] as const)("fetches the %s", async (_name, hook, fetcher) => {
    const { wrapper } = setup()
    const { result } = renderHook(() => hook(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(fetcher).toHaveBeenCalled()
  })
})

describe("Languagarr mutations", () => {
  it("scan stores the results, toasts and invalidates", async () => {
    vi.mocked(api.scanLanguagarr).mockResolvedValue(RESULTS)
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useScanLanguagarr(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(queryClient.getQueryData(queryKeys.languagarrResults)).toEqual(
      RESULTS,
    )
    expect(toast.success).toHaveBeenCalledWith("Languagarr scan complete", {
      description: "4 file(s) without English audio.",
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["languagarr"] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("enqueue reports errors first, then skips, then nothing", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useEnqueueLanguagarr(), { wrapper })

    vi.mocked(api.enqueueLanguagarr).mockResolvedValueOnce({
      queued: 0,
      skipped: 0,
      errors: [{ episode_file_id: 9, error: "Not in scan results" }],
    })
    act(() => result.current.mutate([9]))
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Queued 0 replacement search(es)",
        { description: "1 file(s) not processed — Not in scan results" },
      ),
    )

    vi.mocked(api.enqueueLanguagarr).mockResolvedValueOnce({
      queued: 1,
      skipped: 1,
      errors: [{ episode_file_id: 9, error: "Not in scan results" }],
    })
    act(() => result.current.mutate([1, 9]))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenLastCalledWith(
      "Queued 1 replacement search(es)",
      { description: "1 file(s) not processed — Not in scan results" },
    )

    vi.mocked(api.enqueueLanguagarr).mockResolvedValueOnce({
      queued: 0,
      skipped: 2,
      errors: [],
    })
    act(() => result.current.mutate([1, 2]))
    await waitFor(() =>
      expect(toast.success).toHaveBeenLastCalledWith(
        "Queued 0 replacement search(es)",
        { description: "2 already queued or searched recently." },
      ),
    )

    vi.mocked(api.enqueueLanguagarr).mockResolvedValueOnce({
      queued: 3,
      skipped: 0,
      errors: [],
    })
    act(() => result.current.mutate([1, 2, 3]))
    await waitFor(() =>
      expect(toast.success).toHaveBeenLastCalledWith(
        "Queued 3 replacement search(es)",
        { description: undefined },
      ),
    )
  })

  it("delete toasts success or error depending on per-file errors", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useDeleteLanguagarr(), { wrapper })

    vi.mocked(api.deleteLanguagarr).mockResolvedValueOnce({
      deleted: 1,
      searched: 1,
      failed: 0,
      deleted_ids: [1],
      errors: [],
    })
    act(() => result.current.mutate([1]))
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        "Deleted 1 file(s), searched 1",
        { description: undefined },
      ),
    )

    vi.mocked(api.deleteLanguagarr).mockResolvedValueOnce({
      deleted: 0,
      searched: 0,
      failed: 1,
      deleted_ids: [],
      errors: [{ episode_file_id: 2, error: "File changed since scan" }],
    })
    act(() => result.current.mutate([2]))
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Deleted 0 file(s), searched 0",
        { description: "1 file(s) not processed — File changed since scan" },
      ),
    )
  })

  it("run, clear and settings toast on success", async () => {
    vi.mocked(api.runLanguagarr).mockResolvedValueOnce({
      status: "completed",
      searched: 2,
      failed: 1,
      resolved: 3,
    })
    vi.mocked(api.clearLanguagarrPending).mockResolvedValueOnce({ removed: 3 })
    vi.mocked(api.updateLanguagarrSettings).mockResolvedValueOnce(STATUS)
    const { wrapper } = setup()
    const run = renderHook(() => useRunLanguagarr(), { wrapper }).result
    const clear = renderHook(() => useClearLanguagarrPending(), {
      wrapper,
    }).result
    const save = renderHook(() => useUpdateLanguagarrSettings(), {
      wrapper,
    }).result

    act(() => run.current.mutate())
    act(() => clear.current.mutate())
    act(() => save.current.mutate({ enabled: true }))

    await waitFor(() => expect(save.current.isSuccess).toBe(true))
    await waitFor(() => expect(clear.current.isSuccess).toBe(true))
    await waitFor(() => expect(run.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith("Sent 2 search(es)", {
      description: "1 failed; 3 already resolved.",
    })
    expect(toast.success).toHaveBeenCalledWith("Removed 3 pending search(es)")
    expect(toast.success).toHaveBeenCalledWith("Languagarr settings saved")
  })

  it("run without failures has no description", async () => {
    vi.mocked(api.runLanguagarr).mockResolvedValueOnce({
      status: "idle",
      searched: 0,
      failed: 0,
      resolved: 0,
    })
    const { wrapper } = setup()
    const { result } = renderHook(() => useRunLanguagarr(), { wrapper })
    act(() => result.current.mutate())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith("Sent 0 search(es)", {
      description: undefined,
    })
  })

  it.each([
    [
      "scan",
      useScanLanguagarr,
      api.scanLanguagarr,
      "Languagarr scan failed",
      undefined,
    ],
    [
      "enqueue",
      useEnqueueLanguagarr,
      api.enqueueLanguagarr,
      "Could not queue searches",
      [1],
    ],
    [
      "delete",
      useDeleteLanguagarr,
      api.deleteLanguagarr,
      "Could not delete files",
      [1],
    ],
    [
      "run",
      useRunLanguagarr,
      api.runLanguagarr,
      "Could not run searches",
      undefined,
    ],
    [
      "clear",
      useClearLanguagarrPending,
      api.clearLanguagarrPending,
      "Could not clear the queue",
      undefined,
    ],
    [
      "settings",
      useUpdateLanguagarrSettings,
      api.updateLanguagarrSettings,
      "Could not save Languagarr settings",
      { enabled: true },
    ],
  ] as const)(
    "%s toasts the error",
    async (_name, hook, fetcher, message, variables) => {
      vi.mocked(fetcher).mockRejectedValueOnce(new Error("boom"))
      const { wrapper } = setup()
      const { result } = renderHook(() => hook(), { wrapper })
      act(() => (result.current.mutate as (value: unknown) => void)(variables))
      await waitFor(() => expect(result.current.isError).toBe(true))
      expect(toast.error).toHaveBeenCalledWith(message, { description: "boom" })
    },
  )
})
