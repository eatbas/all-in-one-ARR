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
  getTrendingStatus,
  searchTrending,
  type AddTrendingPayload,
  type TrendingAddResult,
  type TrendingItem,
  type TrendingQuery,
  type TrendingSearchQuery,
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

type TrendingSearchKey = ReturnType<typeof queryKeys.trendingSearch>

/**
 * Whether a previous search's results may stand in for `query` while it
 * fetches: only when the search text changed on the same effective source and
 * media type. Results from another source (e.g. "All" before the user chose
 * "Animation") or media type would show titles, and source links, that the
 * new query may exclude.
 */
function sharesSearchScope(
  previousKey: TrendingSearchKey | undefined,
  query: TrendingSearchQuery,
): boolean {
  if (previousKey === undefined) {
    return false
  }
  const [, , previousSource, previousMedia] = previousKey
  return previousSource === query.source && previousMedia === query.media
}

/**
 * Live title search on one source, gated by `enabled` (the caller decides when
 * the query is long enough). While the search text changes on the same source
 * and media type, the previous results stay in place as placeholder data so the
 * grid never flashes empty mid-typing; a source or media change drops them.
 */
export function useTrendingSearch(
  query: TrendingSearchQuery,
  enabled: boolean,
): UseQueryResult<TrendingItem[]> {
  return useQuery({
    queryKey: queryKeys.trendingSearch(query),
    queryFn: () => searchTrending(query),
    enabled,
    staleTime: TRENDING_STALE_TIME,
    gcTime: TRENDING_GC_TIME,
    placeholderData: (previousData, previousQuery) =>
      sharesSearchScope(previousQuery?.queryKey, query)
        ? previousData
        : undefined,
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
