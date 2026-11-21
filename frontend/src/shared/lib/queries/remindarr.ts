import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query"
import { toast } from "sonner"

import {
  getRemindarrResults,
  getRemindarrSettings,
  getRemindarrStatus,
  getRemindarrTags,
  runRemindarr,
  updateRemindarrSettings,
  type RemindarrResults,
  type RemindarrRunResult,
  type RemindarrSettings,
  type RemindarrSettingsUpdate,
  type RemindarrStatus,
  type RemindarrTag,
} from "@/shared/lib/api"
import { formatCount } from "@/shared/lib/format"
import { queryKeys } from "@/shared/lib/queries/keys"

/** Status refresh while the Remindarr page is open (as Languagarr's page). */
const REMINDARR_REFETCH_INTERVAL = 5_000

/**
 * App-wide status poll behind the nav badge. It reads SQLite and in-memory
 * state only, never Sonarr or Plex.
 */
const REMINDARR_BADGE_REFETCH_INTERVAL = 60_000

/**
 * Results re-read while the page is open, so "New today" rolls over at local
 * midnight; a new refresh generation re-reads them at once.
 */
const REMINDARR_RESULTS_REFETCH_INTERVAL = 60_000

export function useRemindarrStatus(): UseQueryResult<RemindarrStatus> {
  return useQuery({
    queryKey: queryKeys.remindarrStatus,
    queryFn: getRemindarrStatus,
    refetchInterval: REMINDARR_REFETCH_INTERVAL,
  })
}

/** The unwatched count the badge shows, or `null` when it is hidden. */
function badgeCount(status: RemindarrStatus): number | null {
  if (!status.settings.enabled) return null
  return status.counts.unwatched > 0 ? status.counts.unwatched : null
}

/**
 * The nav badge's total-unwatched count. `null` (no badge) while loading, when
 * the status request fails, while Remindarr is disabled, or at zero.
 *
 * A failed refetch keeps the previous `data` in the cache, so the error state
 * is checked as well: an unreachable backend hides a count it can no longer
 * confirm. A successful status that reports stale upstream results still
 * shows its stored count.
 */
export function useRemindarrBadgeCount(): number | null {
  const { data, isError } = useQuery({
    queryKey: queryKeys.remindarrStatus,
    queryFn: getRemindarrStatus,
    refetchInterval: REMINDARR_BADGE_REFETCH_INTERVAL,
    select: badgeCount,
  })
  if (isError) return null
  return data ?? null
}

export function useRemindarrSettings(): UseQueryResult<RemindarrSettings> {
  return useQuery({
    queryKey: queryKeys.remindarrSettings,
    queryFn: getRemindarrSettings,
  })
}

/** Sonarr's tags for the Settings checklist (a live Sonarr read). */
export function useRemindarrTags(): UseQueryResult<RemindarrTag[]> {
  return useQuery({
    queryKey: queryKeys.remindarrTags,
    queryFn: getRemindarrTags,
  })
}

/** The refresh generation the results belong to: the last successful refresh. */
function refreshGeneration(status: RemindarrStatus): string | null {
  return status.last_success_at
}

/**
 * The stored results, kept in step with the polled status.
 *
 * Each successful refresh (manual or scheduled) sets a new `last_success_at`,
 * which is part of the results' key, so the episode rows are re-read as soon
 * as the status poll sees a new generation instead of lingering beside the new
 * counts. A failed refresh keeps the old generation, matching the old rows the
 * backend keeps. The previous rows stay on screen while the next generation
 * loads, and the minute poll re-reads "New today" after local midnight (the
 * server computes it at read time).
 *
 * The results wait for the first status response; `isPending` stays true
 * until then, and remains true if that status request fails.
 */
export function useRemindarrResults(): UseQueryResult<RemindarrResults> {
  const { data: generation } = useQuery({
    queryKey: queryKeys.remindarrStatus,
    queryFn: getRemindarrStatus,
    refetchInterval: REMINDARR_REFETCH_INTERVAL,
    select: refreshGeneration,
  })
  return useQuery({
    queryKey: [...queryKeys.remindarrResults, generation ?? null],
    queryFn: getRemindarrResults,
    enabled: generation !== undefined,
    placeholderData: keepPreviousData,
    refetchInterval: REMINDARR_RESULTS_REFETCH_INTERVAL,
  })
}

function invalidateRemindarr(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["remindarr"] })
  void queryClient.invalidateQueries({ queryKey: queryKeys.activity })
}

export function useUpdateRemindarrSettings(): UseMutationResult<
  RemindarrStatus,
  Error,
  RemindarrSettingsUpdate
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: updateRemindarrSettings,
    onSuccess: () => {
      toast.success("Remindarr settings saved")
      invalidateRemindarr(queryClient)
    },
    onError: (error) => {
      toast.error("Could not save Remindarr settings", {
        description: error.message,
      })
    },
  })
}

export function useRunRemindarr(): UseMutationResult<
  RemindarrRunResult,
  Error,
  void
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: runRemindarr,
    onSuccess: (result) => {
      if (result.status === "disabled") {
        toast.success("Remindarr refresh skipped", {
          description: "Enable Remindarr on the Settings tab to refresh.",
        })
      } else {
        toast.success("Remindarr refreshed", {
          description: `${formatCount(result.unwatched, "unwatched episode")} in ${result.series_with_unwatched} series`,
        })
      }
      invalidateRemindarr(queryClient)
    },
    onError: (error) => {
      // A 409 carries "A Remindarr refresh is already running."; a 502 names
      // the Sonarr or Plex failure. Either way the stored results are kept.
      toast.error("Remindarr refresh failed", { description: error.message })
      invalidateRemindarr(queryClient)
    },
  })
}
