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
  removeTraktList,
  setDryRun,
  startTraktAuth,
  testService,
  testTrakt,
  triggerSync,
  updateGeneralSettings,
  updateServiceSettings,
  updateTraktSettings,
  type ActivityEntry,
  type AddListPayload,
  type DryRunResult,
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
    },
    onError: (error) => {
      toast.error("Could not start authorisation", { description: error.message })
    },
  })
}

export function useTestTrakt(): UseMutationResult<TraktTestResult, Error, void> {
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
  return useMutation({
    mutationFn: (name) => testService(name),
    onSuccess: (result) => {
      if (result.ok) {
        toast.success("Connection OK", { description: result.detail })
      } else {
        toast.error("Connection failed", { description: result.detail })
      }
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
