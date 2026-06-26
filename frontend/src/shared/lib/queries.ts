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
  checkServiceStatuses,
  getActivity,
  getGeneralSettings,
  getItems,
  getLists,
  getServiceSettings,
  getServiceStatuses,
  getStatus,
  getTraktAuthStatus,
  getTraktLists,
  getTraktSettings,
  removeAvailable,
  removeItem,
  removeTraktList,
  startTraktAuth,
  testService,
  testTrakt,
  triggerSync,
  updateGeneralSettings,
  updateServiceSettings,
  updateTraktSettings,
  type ActivityEntry,
  type AddListPayload,
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
      toast.success("Trakt settings saved")
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
      toast.success("Connection saved")
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
            ? "Items are removed from their Trakt list once available in Seer."
            : "Available items stay on their Trakt list until you remove them.",
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
