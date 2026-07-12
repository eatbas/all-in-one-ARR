import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query"
import { toast } from "sonner"

import {
  clearFindarrHistory,
  getFindarrHistory,
  getFindarrSettings,
  getFindarrStatus,
  resetFindarrState,
  runFindarr,
  updateFindarrSettings,
  type FindarrAppName,
  type FindarrCountResult,
  type FindarrHistoryEntry,
  type FindarrRunResult,
  type FindarrSettings,
  type FindarrSettingsUpdate,
  type FindarrStatus,
} from "@/shared/lib/api"
import { queryKeys } from "@/shared/lib/queries/keys"

const FINDARR_REFETCH_INTERVAL = 5_000

export function useFindarrStatus(): UseQueryResult<FindarrStatus> {
  return useQuery({
    queryKey: queryKeys.findarrStatus,
    queryFn: getFindarrStatus,
    refetchInterval: FINDARR_REFETCH_INTERVAL,
  })
}

export function useFindarrSettings(): UseQueryResult<FindarrSettings> {
  return useQuery({
    queryKey: queryKeys.findarrSettings,
    queryFn: getFindarrSettings,
  })
}

export function useFindarrHistory(): UseQueryResult<FindarrHistoryEntry[]> {
  return useQuery({
    queryKey: queryKeys.findarrHistory,
    queryFn: getFindarrHistory,
    refetchInterval: FINDARR_REFETCH_INTERVAL,
  })
}

function invalidateFindarr(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.findarrStatus })
  void queryClient.invalidateQueries({ queryKey: queryKeys.findarrSettings })
  void queryClient.invalidateQueries({ queryKey: queryKeys.findarrHistory })
  void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
}

export function useUpdateFindarrSettings(): UseMutationResult<
  FindarrStatus,
  Error,
  FindarrSettingsUpdate
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: updateFindarrSettings,
    onSuccess: () => {
      toast.success("Findarr settings saved")
      invalidateFindarr(queryClient)
    },
    onError: (error) => {
      toast.error("Could not save Findarr settings", {
        description: error.message,
      })
    },
  })
}

export function useRunFindarr(): UseMutationResult<
  FindarrRunResult,
  Error,
  FindarrAppName | undefined
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (app) => runFindarr(app),
    onSuccess: (result) => {
      toast.success("Findarr run complete", { description: result.detail })
      invalidateFindarr(queryClient)
    },
    onError: (error) => {
      toast.error("Could not run Findarr", { description: error.message })
    },
  })
}

export function useResetFindarrState(): UseMutationResult<
  FindarrCountResult,
  Error,
  void
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: resetFindarrState,
    onSuccess: (result) => {
      toast.success("Findarr state reset", {
        description: `${result.removed} processed entries removed.`,
      })
      invalidateFindarr(queryClient)
    },
    onError: (error) => {
      toast.error("Could not reset Findarr state", {
        description: error.message,
      })
    },
  })
}

export function useClearFindarrHistory(): UseMutationResult<
  FindarrCountResult,
  Error,
  void
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: clearFindarrHistory,
    onSuccess: (result) => {
      toast.success("Findarr history cleared", {
        description: `${result.removed} history entries removed.`,
      })
      invalidateFindarr(queryClient)
    },
    onError: (error) => {
      toast.error("Could not clear Findarr history", {
        description: error.message,
      })
    },
  })
}
