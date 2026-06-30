import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query"
import { toast } from "sonner"

import {
  addTraktList,
  addTrending,
  checkServiceStatuses,
  clearActivity,
  clearFindarrHistory,
  clearItems,
  clearPosters,
  deleteDeletarrItems,
  getActivity,
  getBandwidthStatus,
  getDatabaseStats,
  getDeletarrResults,
  getDeletarrSettings,
  getDeletarrStatus,
  getFindarrHistory,
  getFindarrSettings,
  getFindarrStatus,
  getGeneralSettings,
  getItems,
  getLists,
  getServiceSettings,
  getServiceStatuses,
  getStatus,
  getTraktAuthStatus,
  getTraktLists,
  getTraktSettings,
  getTrending,
  getTrendingRating,
  getTrendingStatus,
  removeAvailable,
  removeItem,
  removeTraktList,
  resetFindarrState,
  runFindarr,
  scanDeletarr,
  startTraktAuth,
  testService,
  testTrakt,
  triggerSync,
  updateBandwidthSettings,
  updateDeletarrSettings,
  updateFindarrSettings,
  updateGeneralSettings,
  updateServiceSettings,
  updateTraktSettings,
  type ActivityEntry,
  type AddListPayload,
  type BandwidthSettingsUpdate,
  type BandwidthStatus,
  type DatabaseStats,
  type DeletarrDeleteResult,
  type DeletarrLibraryType,
  type DeletarrResults,
  type DeletarrSettings,
  type DeletarrSettingsUpdate,
  type DeletarrStatus,
  type FindarrAppName,
  type FindarrCountResult,
  type FindarrHistoryEntry,
  type FindarrRunResult,
  type FindarrSettings,
  type FindarrSettingsUpdate,
  type FindarrStatus,
  type GeneralSettings,
  type Item,
  type ListSummary,
  type ServiceName,
  type ServicesSettings,
  type ServicesStatusResponse,
  type ServiceTestResult,
  type Status,
  type SyncResult,
  type TraktAuthStart,
  type TraktAuthStatus,
  type TraktListEntry,
  type TraktSettings,
  type TraktTestResult,
  type AddTrendingPayload,
  type TrendingAddResult,
  type TrendingItem,
  type TrendingQuery,
  type TrendingRating,
  type TrendingStatus,
  type UpdateGeneralSettings,
  type UpdateServicePayload,
  type UpdateTraktSettings,
} from "@/shared/lib/api"

/** Polling interval (ms) shared by all dashboard queries. */
const REFETCH_INTERVAL = 10_000

/** While device auth is pending, poll the status this often (ms). */
const AUTH_POLL_INTERVAL = 2_000

/** Stable query keys so mutations can target invalidations precisely. */
export const queryKeys = {
  status: ["status"] as const,
  activity: ["activity"] as const,
  lists: ["lists"] as const,
  listItems: (slug: string) => ["items", "by-list", slug] as const,
  traktSettings: ["trakt", "settings"] as const,
  traktAuthStatus: ["trakt", "auth-status"] as const,
  traktLists: ["trakt", "lists"] as const,
  services: ["services"] as const,
  serviceStatuses: ["service-statuses"] as const,
  generalSettings: ["general", "settings"] as const,
  database: ["database", "stats"] as const,
  bandwidthStatus: ["bandwidth", "status"] as const,
  deletarrStatus: ["deletarr", "status"] as const,
  deletarrSettings: ["deletarr", "settings"] as const,
  deletarrResults: (type: DeletarrLibraryType) =>
    ["deletarr", "results", type] as const,
  findarrStatus: ["findarr", "status"] as const,
  findarrSettings: ["findarr", "settings"] as const,
  findarrHistory: ["findarr", "history"] as const,
  trending: (query: TrendingQuery) =>
    ["trending", query.source, query.media, query.category] as const,
  trendingRating: (key: string) => ["trending", "rating", key] as const,
  trendingStatus: ["trending", "status"] as const,
}

export function useStatus(): UseQueryResult<Status> {
  return useQuery({
    queryKey: queryKeys.status,
    queryFn: getStatus,
    refetchInterval: REFETCH_INTERVAL,
  })
}

export function useLists(): UseQueryResult<ListSummary[]> {
  return useQuery({
    queryKey: queryKeys.lists,
    queryFn: getLists,
    refetchInterval: REFETCH_INTERVAL,
  })
}

/** Items for one synced list, fetched lazily (only while ``enabled``). */
export function useListItems(
  slug: string,
  enabled: boolean,
): UseQueryResult<Item[]> {
  return useQuery({
    queryKey: queryKeys.listItems(slug),
    queryFn: () => getItems(undefined, slug),
    enabled,
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
    onSuccess: async () => {
      toast.success("Sync complete", {
        description: "The latest sync run has finished.",
      })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.status }),
        queryClient.invalidateQueries({ queryKey: ["items"] }),
        queryClient.invalidateQueries({ queryKey: queryKeys.lists }),
        queryClient.invalidateQueries({ queryKey: queryKeys.activity }),
      ])
    },
    onError: (error) => {
      toast.error("Could not trigger sync", { description: error.message })
    },
  })
}

export function useTraktSettings(): UseQueryResult<TraktSettings> {
  return useQuery({
    queryKey: queryKeys.traktSettings,
    queryFn: getTraktSettings,
  })
}

export function useTraktAuthStatus(): UseQueryResult<TraktAuthStatus> {
  return useQuery({
    queryKey: queryKeys.traktAuthStatus,
    queryFn: getTraktAuthStatus,
    // Poll only while an authorisation attempt is in progress.
    refetchInterval: (query) =>
      query.state.data?.state === "pending" ? AUTH_POLL_INTERVAL : false,
  })
}

export function useTraktLists(enabled: boolean): UseQueryResult<TraktListEntry[]> {
  return useQuery({
    queryKey: queryKeys.traktLists,
    queryFn: getTraktLists,
    enabled,
  })
}

export function useUpdateTraktSettings(): UseMutationResult<
  TraktSettings,
  Error,
  UpdateTraktSettings
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: updateTraktSettings,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.traktSettings })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not save Trakt settings", { description: error.message })
    },
  })
}

export function useStartTraktAuth(): UseMutationResult<TraktAuthStart, Error, void> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: startTraktAuth,
    onSuccess: () => {
      toast.success("Authorisation started", {
        description: "Enter the code shown below at trakt.tv/activate.",
      })
      void queryClient.invalidateQueries({ queryKey: queryKeys.traktAuthStatus })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not start authorisation", { description: error.message })
    },
  })
}

export function useTestTrakt(): UseMutationResult<TraktTestResult, Error, void> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: testTrakt,
    onSuccess: (result) => {
      if (result.ok) {
        toast.success("Trakt connection OK", {
          description: result.user ? `Signed in as ${result.user}` : undefined,
        })
      } else {
        toast.error("Trakt connection failed", { description: result.message })
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not test connection", { description: error.message })
    },
  })
}

export function useAddTraktList(): UseMutationResult<
  TraktSettings,
  Error,
  AddListPayload
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: addTraktList,
    onSuccess: () => {
      toast.success("List added")
      void queryClient.invalidateQueries({ queryKey: queryKeys.traktSettings })
      void queryClient.invalidateQueries({ queryKey: queryKeys.traktLists })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not add list", { description: error.message })
    },
  })
}

export function useRemoveTraktList(): UseMutationResult<
  TraktSettings,
  Error,
  { owner_user: string; slug: string }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ owner_user, slug }) => removeTraktList(owner_user, slug),
    onSuccess: () => {
      toast.success("List removed")
      void queryClient.invalidateQueries({ queryKey: queryKeys.traktSettings })
      void queryClient.invalidateQueries({ queryKey: queryKeys.traktLists })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not remove list", { description: error.message })
    },
  })
}

export function useServiceSettings(): UseQueryResult<ServicesSettings> {
  return useQuery({
    queryKey: queryKeys.services,
    queryFn: getServiceSettings,
  })
}

export function useUpdateServiceSettings(): UseMutationResult<
  ServicesSettings,
  Error,
  { name: ServiceName; body: UpdateServicePayload }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ name, body }) => updateServiceSettings(name, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.services })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not save connection", { description: error.message })
    },
  })
}

export function useTestService(): UseMutationResult<
  ServiceTestResult,
  Error,
  ServiceName
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (name) => testService(name),
    onSuccess: (result) => {
      if (result.ok) {
        toast.success("Connection OK", { description: result.detail })
      } else {
        toast.error("Connection failed", { description: result.detail })
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not test connection", { description: error.message })
    },
  })
}

export function useServiceStatuses(): UseQueryResult<ServicesStatusResponse> {
  return useQuery({
    queryKey: queryKeys.serviceStatuses,
    queryFn: getServiceStatuses,
    refetchInterval: (query) =>
      (query.state.data?.interval_seconds ?? 60) * 1000,
  })
}

export function useCheckServiceStatuses(): UseMutationResult<
  ServicesStatusResponse,
  Error,
  void
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: checkServiceStatuses,
    onSuccess: () => {
      toast.success("Status check complete")
      void queryClient.invalidateQueries({ queryKey: queryKeys.serviceStatuses })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Status check failed", { description: error.message })
    },
  })
}

export function useUpdateStatusInterval(): UseMutationResult<
  GeneralSettings,
  Error,
  UpdateGeneralSettings
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: updateGeneralSettings,
    onSuccess: (result) => {
      toast.success("Status interval updated", {
        description: `Checking every ${result.interval_seconds} seconds`,
      })
      void queryClient.invalidateQueries({ queryKey: queryKeys.serviceStatuses })
      void queryClient.invalidateQueries({ queryKey: queryKeys.generalSettings })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not update interval", { description: error.message })
    },
  })
}

export function useGeneralSettings(): UseQueryResult<GeneralSettings> {
  return useQuery({
    queryKey: queryKeys.generalSettings,
    queryFn: getGeneralSettings,
  })
}

export function useUpdateSyncInterval(): UseMutationResult<
  GeneralSettings,
  Error,
  number
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (minutes) =>
      updateGeneralSettings({ sync_interval_minutes: minutes }),
    onSuccess: (result) => {
      toast.success("Sync interval updated", {
        description: `Polling Trakt every ${result.sync_interval_minutes} minutes`,
      })
      void queryClient.invalidateQueries({ queryKey: queryKeys.generalSettings })
      void queryClient.invalidateQueries({ queryKey: queryKeys.lists })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not update sync interval", { description: error.message })
    },
  })
}

export function useUpdateTrendingInterval(): UseMutationResult<
  GeneralSettings,
  Error,
  number
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (minutes) =>
      updateGeneralSettings({ trending_sync_interval_minutes: minutes }),
    onSuccess: (result) => {
      toast.success("Trending sync interval updated", {
        description: `Refreshing trending every ${result.trending_sync_interval_minutes} minutes`,
      })
      void queryClient.invalidateQueries({ queryKey: queryKeys.generalSettings })
      void queryClient.invalidateQueries({ queryKey: queryKeys.trendingStatus })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not update trending sync interval", {
        description: error.message,
      })
    },
  })
}

export function useUpdateAutoRemoveWhenAvailable(): UseMutationResult<
  GeneralSettings,
  Error,
  boolean
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (enabled) =>
      updateGeneralSettings({ auto_remove_when_available: enabled }),
    onSuccess: (result) => {
      toast.success(
        result.auto_remove_when_available
          ? "Auto-remove when available enabled"
          : "Auto-remove when available disabled",
        {
          description: result.auto_remove_when_available
            ? "Items are removed from their Trakt list once available (or partially available) in Seer."
            : "Items stay on their Trakt list until you remove them.",
        },
      )
      void queryClient.invalidateQueries({ queryKey: queryKeys.generalSettings })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not update auto-remove", { description: error.message })
    },
  })
}

export function useRemoveItem(): UseMutationResult<
  void,
  Error,
  { list_id: string; trakt_id: number }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ list_id, trakt_id }) => removeItem(list_id, trakt_id),
    onSuccess: () => {
      toast.success("Item removed from the Trakt list")
      void queryClient.invalidateQueries({ queryKey: ["items"] })
      void queryClient.invalidateQueries({ queryKey: queryKeys.lists })
      void queryClient.invalidateQueries({ queryKey: queryKeys.status })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not remove item", { description: error.message })
    },
  })
}

export function useRemoveAvailable(): UseMutationResult<SyncResult, Error, void> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: removeAvailable,
    onSuccess: () => {
      toast.success("Removing available items", {
        description: "Available items are being removed from their Trakt lists.",
      })
      void queryClient.invalidateQueries({ queryKey: ["items"] })
      void queryClient.invalidateQueries({ queryKey: queryKeys.lists })
      void queryClient.invalidateQueries({ queryKey: queryKeys.status })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
    },
    onError: (error) => {
      toast.error("Could not remove available items", {
        description: error.message,
      })
    },
  })
}

export function useDatabaseStats(): UseQueryResult<DatabaseStats> {
  return useQuery({
    queryKey: queryKeys.database,
    queryFn: getDatabaseStats,
  })
}

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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.bandwidthStatus })
    },
    onError: (error) => {
      toast.error("Could not update bandwidth settings", {
        description: error.message,
      })
    },
  })
}

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
      toast.error("Could not reset Findarr state", { description: error.message })
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
      toast.error("Could not clear Findarr history", { description: error.message })
    },
  })
}

function invalidateDatabase(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.database })
  void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
}

export function useClearActivity(): UseMutationResult<DatabaseStats, Error, void> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: clearActivity,
    onSuccess: () => {
      toast.success("Activity log cleared")
      invalidateDatabase(queryClient)
    },
    onError: (error) => {
      toast.error("Could not clear activity log", { description: error.message })
    },
  })
}

export function useClearItems(): UseMutationResult<DatabaseStats, Error, void> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: clearItems,
    onSuccess: () => {
      toast.success("Synced items cleared", {
        description: "Tracked items and sync state were removed.",
      })
      invalidateDatabase(queryClient)
      void queryClient.invalidateQueries({ queryKey: queryKeys.lists })
      void queryClient.invalidateQueries({ queryKey: queryKeys.status })
      void queryClient.invalidateQueries({ queryKey: ["items"] })
    },
    onError: (error) => {
      toast.error("Could not clear synced items", { description: error.message })
    },
  })
}

export function useClearPosters(): UseMutationResult<DatabaseStats, Error, void> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: clearPosters,
    onSuccess: () => {
      toast.success("Poster cache cleared")
      invalidateDatabase(queryClient)
    },
    onError: (error) => {
      toast.error("Could not clear poster cache", { description: error.message })
    },
  })
}

const DELETARR_REFETCH_INTERVAL = 5_000

export function useDeletarrStatus(): UseQueryResult<DeletarrStatus> {
  return useQuery({
    queryKey: queryKeys.deletarrStatus,
    queryFn: getDeletarrStatus,
    refetchInterval: DELETARR_REFETCH_INTERVAL,
  })
}

export function useDeletarrSettings(): UseQueryResult<DeletarrSettings> {
  return useQuery({
    queryKey: queryKeys.deletarrSettings,
    queryFn: getDeletarrSettings,
  })
}

export function useDeletarrResults(
  type: DeletarrLibraryType,
): UseQueryResult<DeletarrResults> {
  return useQuery({
    queryKey: queryKeys.deletarrResults(type),
    queryFn: () => getDeletarrResults(type),
    refetchInterval: DELETARR_REFETCH_INTERVAL,
  })
}

function invalidateDeletarr(
  queryClient: ReturnType<typeof useQueryClient>,
  type?: DeletarrLibraryType,
) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.deletarrStatus })
  void queryClient.invalidateQueries({ queryKey: queryKeys.deletarrSettings })
  if (type) {
    void queryClient.invalidateQueries({ queryKey: queryKeys.deletarrResults(type) })
  } else {
    void queryClient.invalidateQueries({ queryKey: ["deletarr", "results"] })
  }
  void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
}

export function useUpdateDeletarrSettings(): UseMutationResult<
  DeletarrStatus,
  Error,
  DeletarrSettingsUpdate
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: updateDeletarrSettings,
    onSuccess: () => {
      toast.success("Deletarr settings saved")
      invalidateDeletarr(queryClient)
    },
    onError: (error) => {
      toast.error("Could not save Deletarr settings", {
        description: error.message,
      })
    },
  })
}

export function useScanDeletarr(): UseMutationResult<
  DeletarrResults,
  Error,
  DeletarrLibraryType
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: scanDeletarr,
    onSuccess: (result) => {
      toast.success("Deletarr scan complete", {
        description: `${result.results.length} candidate(s) found.`,
      })
      invalidateDeletarr(queryClient, result.type)
    },
    onError: (error) => {
      toast.error("Could not scan library", { description: error.message })
    },
  })
}

export function useDeleteDeletarrItems(): UseMutationResult<
  DeletarrDeleteResult,
  Error,
  { type: DeletarrLibraryType; paths: string[] }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ type, paths }) => deleteDeletarrItems(type, paths),
    onSuccess: (result, variables) => {
      if (result.failed > 0) {
        toast.error("Some Deletarr items could not be deleted", {
          description: `${result.deleted} deleted, ${result.failed} failed.`,
        })
      } else {
        toast.success("Deletarr items deleted", {
          description: `${result.deleted} item(s), ${result.freed_formatted} reclaimed.`,
        })
      }
      invalidateDeletarr(queryClient, variables.type)
    },
    onError: (error) => {
      toast.error("Could not delete selected items", {
        description: error.message,
      })
    },
  })
}

/**
 * Trending feeds change slowly, so they are cached for several minutes rather
 * than polled on the shared dashboard interval (which would hammer the external
 * APIs).
 */
const TRENDING_STALE_TIME = 5 * 60_000

export function useTrending(query: TrendingQuery): UseQueryResult<TrendingItem[]> {
  return useQuery({
    queryKey: queryKeys.trending(query),
    queryFn: () => getTrending(query),
    staleTime: TRENDING_STALE_TIME,
  })
}

/**
 * Poll the scheduled trending-sync status so the Trending page can show when the
 * snapshot was last refreshed. Refetched on the shared interval (the relative-time
 * label should not drift far from the real refresh time).
 */
export function useTrendingStatus(): UseQueryResult<TrendingStatus> {
  return useQuery({
    queryKey: queryKeys.trendingStatus,
    queryFn: getTrendingStatus,
    refetchInterval: REFETCH_INTERVAL,
  })
}

/**
 * Fetch the IMDb rating overlay for one trending item, lazily. Disabled when the
 * item carries no usable id; the backend caches results, so the rating is fetched
 * at most once per id regardless of how often a card re-renders.
 */
export function useTrendingRating(
  item: Pick<TrendingItem, "imdb" | "media_type" | "tmdb">,
  enabled: boolean,
): UseQueryResult<TrendingRating> {
  const hasId = item.imdb !== null || item.tmdb !== null
  const key = item.imdb ?? `${item.media_type}:${item.tmdb}`
  return useQuery({
    queryKey: queryKeys.trendingRating(key),
    queryFn: () =>
      getTrendingRating({ imdb: item.imdb, media: item.media_type, tmdb: item.tmdb }),
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
