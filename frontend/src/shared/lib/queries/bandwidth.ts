import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query"
import { toast } from "sonner"

import {
  getBandwidthStatus,
  setBandwidthClientPaused,
  updateBandwidthSettings,
  type BandwidthClient,
  type BandwidthSettingsUpdate,
  type BandwidthStatus,
} from "@/shared/lib/api"
import { queryKeys } from "@/shared/lib/queries/keys"

/** Polling interval (ms) for the Bandwidth-Controllarr status page. */
const BANDWIDTH_REFETCH_INTERVAL = 3_000

export function useBandwidthStatus(): UseQueryResult<BandwidthStatus> {
  return useQuery({
    queryKey: queryKeys.bandwidthStatus,
    queryFn: getBandwidthStatus,
    refetchInterval: BANDWIDTH_REFETCH_INTERVAL,
  })
}

export function useUpdateBandwidthSettings(): UseMutationResult<
  BandwidthStatus,
  Error,
  BandwidthSettingsUpdate
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: updateBandwidthSettings,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.bandwidthStatus }),
    onError: (error) => {
      toast.error("Could not update bandwidth settings", {
        description: error.message,
      })
    },
  })
}

export function useSetBandwidthClientPaused(): UseMutationResult<
  BandwidthStatus,
  Error,
  { client: BandwidthClient; paused: boolean }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ client, paused }) =>
      setBandwidthClientPaused(client, paused),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.bandwidthStatus }),
    onError: (error) => {
      toast.error("Could not update downloader", {
        description: error.message,
      })
    },
  })
}
