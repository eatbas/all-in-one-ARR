import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query"
import { toast } from "sonner"

import {
  ApiError,
  cleanarrErrorMessage,
  clearCleanarrStrikes,
  getCleanarrHistory,
  getCleanarrQueue,
  getCleanarrSettings,
  getCleanarrStatus,
  ignoreCleanarrDownload,
  runCleanarr,
  updateCleanarrSettings,
  type CleanarrCountResult,
  type CleanarrHistoryEntry,
  type CleanarrQueue,
  type CleanarrRunResult,
  type CleanarrSettings,
  type CleanarrSettingsUpdate,
  type CleanarrStatus,
} from "@/shared/lib/api"
import { queryKeys } from "@/shared/lib/queries/keys"

const CLEANARR_REFETCH_INTERVAL = 5_000
// The queue view reads Sonarr, Radarr and SABnzbd live, so it polls less often.
const CLEANARR_QUEUE_REFETCH_INTERVAL = 30_000

/** A queue item to ignore, with its title for the confirmation toast. */
export interface CleanarrIgnoreTarget {
  downloadId: string
  title: string
}

export function useCleanarrStatus(): UseQueryResult<CleanarrStatus> {
  return useQuery({
    queryKey: queryKeys.cleanarrStatus,
    queryFn: getCleanarrStatus,
    refetchInterval: CLEANARR_REFETCH_INTERVAL,
  })
}

export function useCleanarrSettings(): UseQueryResult<CleanarrSettings> {
  return useQuery({
    queryKey: queryKeys.cleanarrSettings,
    queryFn: getCleanarrSettings,
  })
}

export function useCleanarrQueue(): UseQueryResult<CleanarrQueue> {
  return useQuery({
    queryKey: queryKeys.cleanarrQueue,
    queryFn: getCleanarrQueue,
    refetchInterval: CLEANARR_QUEUE_REFETCH_INTERVAL,
  })
}

export function useCleanarrHistory(): UseQueryResult<CleanarrHistoryEntry[]> {
  return useQuery({
    queryKey: queryKeys.cleanarrHistory,
    queryFn: getCleanarrHistory,
    refetchInterval: CLEANARR_REFETCH_INTERVAL,
  })
}

function invalidateCleanarr(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["cleanarr"] })
  void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
}

/**
 * Toast a failed run, strike reset or ignore: a 409 means a run is in
 * progress, which is a wait-and-retry warning rather than an error.
 */
function toastBusyOrError(error: Error, title: string): void {
  if (error instanceof ApiError && error.status === 409) {
    toast.warning("Cleanarr is already running", {
      description: "Try again when the current run finishes.",
    })
    return
  }
  toast.error(title, { description: error.message })
}

export function useUpdateCleanarrSettings(): UseMutationResult<
  CleanarrStatus,
  Error,
  CleanarrSettingsUpdate
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: updateCleanarrSettings,
    onSuccess: () => {
      toast.success("Cleanarr settings saved")
      invalidateCleanarr(queryClient)
    },
    onError: (error) => {
      toast.error("Could not save Cleanarr settings", {
        description: cleanarrErrorMessage(error),
      })
    },
  })
}

export function useRunCleanarr(): UseMutationResult<
  CleanarrRunResult,
  Error,
  void
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: runCleanarr,
    onSuccess: (result) => {
      toast.success(
        result.status === "skipped"
          ? "Cleanarr run skipped"
          : "Cleanarr run complete",
        { description: result.detail },
      )
      invalidateCleanarr(queryClient)
    },
    onError: (error) => toastBusyOrError(error, "Could not run Cleanarr"),
  })
}

export function useClearCleanarrStrikes(): UseMutationResult<
  CleanarrCountResult,
  Error,
  void
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: clearCleanarrStrikes,
    onSuccess: (result) => {
      toast.success(`Cleared ${result.count} strike(s)`)
      invalidateCleanarr(queryClient)
    },
    onError: (error) => toastBusyOrError(error, "Could not clear strikes"),
  })
}

export function useIgnoreCleanarrDownload(): UseMutationResult<
  CleanarrSettings,
  Error,
  CleanarrIgnoreTarget
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ downloadId }) => ignoreCleanarrDownload(downloadId),
    onSuccess: (_settings, { title }) => {
      toast.success("Ignoring download", {
        description: `Cleanarr will skip ${title} from now on.`,
      })
      invalidateCleanarr(queryClient)
    },
    onError: (error) => toastBusyOrError(error, "Could not ignore download"),
  })
}
