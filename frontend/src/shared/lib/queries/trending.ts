import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query"
import { toast } from "sonner"

import {
  addTrending,
  getTrending,
  getTrendingRating,
  getTrendingStatus,
  type AddTrendingPayload,
  type TrendingAddResult,
  type TrendingItem,
  type TrendingQuery,
  type TrendingRating,
  type TrendingStatus,
} from "@/shared/lib/api"
import { queryKeys } from "@/shared/lib/queries/keys"

/** Trending feeds change slowly and should not poll external APIs. */
const TRENDING_STALE_TIME = 5 * 60_000
const TRENDING_GC_TIME = 60 * 60_000
const TRENDING_STATUS_REFETCH_INTERVAL = 10_000

export function useTrending(
  query: TrendingQuery,
): UseQueryResult<TrendingItem[]> {
  return useQuery({
    queryKey: queryKeys.trending(query),
    queryFn: () => getTrending(query),
    staleTime: TRENDING_STALE_TIME,
    gcTime: TRENDING_GC_TIME,
  })
}

/** Poll the scheduled snapshot status without refetching the feed itself. */
export function useTrendingStatus(): UseQueryResult<TrendingStatus> {
  return useQuery({
    queryKey: queryKeys.trendingStatus,
    queryFn: getTrendingStatus,
    refetchInterval: TRENDING_STATUS_REFETCH_INTERVAL,
  })
}

export function useTrendingRating(
  item: Pick<TrendingItem, "imdb" | "media_type" | "tmdb">,
  enabled: boolean,
): UseQueryResult<TrendingRating> {
  const hasId = item.imdb !== null || item.tmdb !== null
  const key = item.imdb ?? `${item.media_type}:${item.tmdb}`
  return useQuery({
    queryKey: queryKeys.trendingRating(key),
    queryFn: () =>
      getTrendingRating({
        imdb: item.imdb,
        media: item.media_type,
        tmdb: item.tmdb,
      }),
    enabled: enabled && hasId,
    staleTime: Infinity,
  })
}

export function useAddTrending(): UseMutationResult<
  TrendingAddResult,
  Error,
  AddTrendingPayload
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: addTrending,
    onSuccess: (result) => {
      if (result.status === "added_pending_sync") {
        toast.success("Added to Trakt list", {
          description:
            "A sync is already running; the item will be requested on the next poll.",
        })
      } else {
        toast.success("Added to Trakt list", {
          description: "Syncing now to request it in Seer.",
        })
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.status })
      void queryClient.invalidateQueries({ queryKey: queryKeys.lists })
      void queryClient.invalidateQueries({ queryKey: ["items"] })
      void queryClient.invalidateQueries({ queryKey: ["trending"] })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not add to list", { description: error.message })
    },
  })
}
