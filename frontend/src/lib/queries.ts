import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query"
import { toast } from "sonner"

import {
  getActivity,
  getItems,
  getStatus,
  setDryRun,
  triggerSync,
  type ActivityEntry,
  type DryRunResult,
  type Item,
  type ItemStatus,
  type Status,
  type SyncResult,
} from "@/lib/api"

/** Polling interval (ms) shared by all dashboard queries. */
const REFETCH_INTERVAL = 10_000

/** Stable query keys so mutations can target invalidations precisely. */
export const queryKeys = {
  status: ["status"] as const,
  activity: ["activity"] as const,
  items: (status?: ItemStatus) => ["items", status ?? "all"] as const,
}

export function useStatus(): UseQueryResult<Status> {
  return useQuery({
    queryKey: queryKeys.status,
    queryFn: getStatus,
    refetchInterval: REFETCH_INTERVAL,
  })
}

export function useItems(status?: ItemStatus): UseQueryResult<Item[]> {
  return useQuery({
    queryKey: queryKeys.items(status),
    queryFn: () => getItems(status),
    refetchInterval: REFETCH_INTERVAL,
  })
}

export function useActivity(): UseQueryResult<ActivityEntry[]> {
  return useQuery({
    queryKey: queryKeys.activity,
    queryFn: getActivity,
    refetchInterval: REFETCH_INTERVAL,
  })
}

export function useSyncNow(): UseMutationResult<SyncResult, Error, void> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: triggerSync,
    onSuccess: () => {
      toast.success("Sync triggered", {
        description: "A sync run has been queued on the backend.",
      })
      void queryClient.invalidateQueries({ queryKey: queryKeys.status })
      void queryClient.invalidateQueries({ queryKey: ["items"] })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not trigger sync", { description: error.message })
    },
  })
}

export function useSetDryRun(): UseMutationResult<DryRunResult, Error, boolean> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: setDryRun,
    onSuccess: (result) => {
      toast.success(
        result.dry_run ? "Dry-run mode enabled" : "Dry-run mode disabled",
        {
          description: result.dry_run
            ? "Side-effecting actions are only logged, not executed."
            : "Live mode: requests and removals will be executed.",
        },
      )
      void queryClient.invalidateQueries({ queryKey: queryKeys.status })
    },
    onError: (error) => {
      toast.error("Could not change dry-run mode", {
        description: error.message,
      })
    },
  })
}
