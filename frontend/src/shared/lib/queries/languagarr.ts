import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query"
import { toast } from "sonner"

import {
  clearLanguagarrPending,
  deleteLanguagarr,
  enqueueLanguagarr,
  getLanguagarrQueue,
  getLanguagarrResults,
  getLanguagarrSettings,
  getLanguagarrStatus,
  runLanguagarr,
  scanLanguagarr,
  updateLanguagarrSettings,
  type LanguagarrClearPendingResult,
  type LanguagarrDeleteResult,
  type LanguagarrEnqueueResult,
  type LanguagarrQueue,
  type LanguagarrResults,
  type LanguagarrRunResult,
  type LanguagarrSettings,
  type LanguagarrSettingsUpdate,
  type LanguagarrStatus,
} from "@/shared/lib/api"
import { queryKeys } from "@/shared/lib/queries/keys"

const LANGUAGARR_REFETCH_INTERVAL = 5_000

export function useLanguagarrStatus(): UseQueryResult<LanguagarrStatus> {
  return useQuery({
    queryKey: queryKeys.languagarrStatus,
    queryFn: getLanguagarrStatus,
    refetchInterval: LANGUAGARR_REFETCH_INTERVAL,
  })
}

export function useLanguagarrSettings(): UseQueryResult<LanguagarrSettings> {
  return useQuery({
    queryKey: queryKeys.languagarrSettings,
    queryFn: getLanguagarrSettings,
  })
}

export function useLanguagarrResults(): UseQueryResult<LanguagarrResults> {
  return useQuery({
    queryKey: queryKeys.languagarrResults,
    queryFn: getLanguagarrResults,
  })
}

export function useLanguagarrQueue(): UseQueryResult<LanguagarrQueue> {
  return useQuery({
    queryKey: queryKeys.languagarrQueue,
    queryFn: getLanguagarrQueue,
    refetchInterval: LANGUAGARR_REFETCH_INTERVAL,
  })
}

function invalidateLanguagarr(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["languagarr"] })
  void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
}

/** Toast body listing how many files were rejected and the first reason. */
function errorSummary(errors: { error: string }[]): string | undefined {
  if (errors.length === 0) return undefined
  return `${errors.length} file(s) not processed — ${errors[0].error}`
}

export function useUpdateLanguagarrSettings(): UseMutationResult<
  LanguagarrStatus,
  Error,
  LanguagarrSettingsUpdate
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: updateLanguagarrSettings,
    onSuccess: () => {
      toast.success("Languagarr settings saved")
      invalidateLanguagarr(queryClient)
    },
    onError: (error) => {
      toast.error("Could not save Languagarr settings", {
        description: error.message,
      })
    },
  })
}

export function useScanLanguagarr(): UseMutationResult<
  LanguagarrResults,
  Error,
  void
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: scanLanguagarr,
    onSuccess: (result) => {
      queryClient.setQueryData(queryKeys.languagarrResults, result)
      toast.success("Languagarr scan complete", {
        description: `${result.scan.non_compliant} file(s) without English audio.`,
      })
      invalidateLanguagarr(queryClient)
    },
    onError: (error) => {
      toast.error("Languagarr scan failed", { description: error.message })
    },
  })
}

export function useEnqueueLanguagarr(): UseMutationResult<
  LanguagarrEnqueueResult,
  Error,
  number[]
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: enqueueLanguagarr,
    onSuccess: (result) => {
      // Nothing queued and something rejected is a failure, not a success.
      const notify =
        result.queued === 0 && result.errors.length > 0
          ? toast.error
          : toast.success
      notify(`Queued ${result.queued} replacement search(es)`, {
        description:
          errorSummary(result.errors) ??
          (result.skipped
            ? `${result.skipped} already queued or searched recently.`
            : undefined),
      })
      invalidateLanguagarr(queryClient)
    },
    onError: (error) => {
      toast.error("Could not queue searches", { description: error.message })
    },
  })
}

export function useDeleteLanguagarr(): UseMutationResult<
  LanguagarrDeleteResult,
  Error,
  number[]
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: deleteLanguagarr,
    onSuccess: (result) => {
      const notify = result.errors.length ? toast.error : toast.success
      notify(`Deleted ${result.deleted} file(s), searched ${result.searched}`, {
        description: errorSummary(result.errors),
      })
      invalidateLanguagarr(queryClient)
    },
    onError: (error) => {
      toast.error("Could not delete files", { description: error.message })
    },
  })
}

export function useRunLanguagarr(): UseMutationResult<
  LanguagarrRunResult,
  Error,
  void
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: runLanguagarr,
    onSuccess: (result) => {
      const notes = [
        result.failed ? `${result.failed} failed` : "",
        result.resolved ? `${result.resolved} already resolved` : "",
      ].filter(Boolean)
      toast.success(`Sent ${result.searched} search(es)`, {
        description: notes.length ? `${notes.join("; ")}.` : undefined,
      })
      invalidateLanguagarr(queryClient)
    },
    onError: (error) => {
      toast.error("Could not run searches", { description: error.message })
    },
  })
}

export function useClearLanguagarrPending(): UseMutationResult<
  LanguagarrClearPendingResult,
  Error,
  void
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: clearLanguagarrPending,
    onSuccess: (result) => {
      toast.success(`Removed ${result.removed} pending search(es)`)
      invalidateLanguagarr(queryClient)
    },
    onError: (error) => {
      toast.error("Could not clear the queue", { description: error.message })
    },
  })
}
