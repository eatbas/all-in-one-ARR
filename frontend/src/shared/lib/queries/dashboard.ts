import { useEffect } from "react"
import {
  keepPreviousData,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query"

import {
  getDashboardHistory,
  getDashboardSummary,
  type DashboardHistory,
  type DashboardRange,
  type DashboardSummary,
} from "@/shared/lib/api"
import { queryKeys } from "@/shared/lib/queries/keys"

/** Polling interval (ms) for the dashboard summary; matches the backend cache. */
const DASHBOARD_SUMMARY_REFETCH_INTERVAL = 60_000

/**
 * Live dashboard statistics, polled every minute while the tab is visible
 * (`refetchIntervalInBackground: false` pauses polling in hidden tabs).
 */
export function useDashboardSummary(): UseQueryResult<DashboardSummary> {
  return useQuery({
    queryKey: queryKeys.dashboardSummary,
    queryFn: getDashboardSummary,
    refetchInterval: DASHBOARD_SUMMARY_REFETCH_INTERVAL,
    refetchIntervalInBackground: false,
  })
}

/**
 * Daily-snapshot trends for one range. Each range has its own cache entry, and
 * the previous range stays on screen while a new one loads.
 *
 * History only changes when a snapshot is written, so it is never refetched on
 * a timer or on focus. Instead, `latestSnapshotAt` (the polled summary's
 * snapshot version) is compared with the version the loaded history reflects:
 * when they differ — the start-up catch-up finished after this history was
 * fetched, or a later daily snapshot landed — every range is invalidated, so
 * the shown range refetches and the others refetch when next shown.
 * `undefined` (summary not loaded or failed) never triggers a refresh.
 */
export function useDashboardHistory(
  days: DashboardRange,
  latestSnapshotAt?: string | null,
): UseQueryResult<DashboardHistory> {
  const queryClient = useQueryClient()
  const history = useQuery({
    queryKey: queryKeys.dashboardHistory(days),
    queryFn: () => getDashboardHistory(days),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
  })
  // A placeholder belongs to another range, so its version says nothing here.
  const loadedSnapshotAt = history.isPlaceholderData
    ? undefined
    : history.data?.latest_snapshot_at

  useEffect(() => {
    if (latestSnapshotAt === undefined || loadedSnapshotAt === undefined) {
      return
    }
    if (latestSnapshotAt !== loadedSnapshotAt) {
      // Refetch failures surface through the query's error state; the promise
      // itself never rejects (no `throwOnError`).
      void queryClient.invalidateQueries({
        queryKey: queryKeys.dashboardHistoryAll,
      })
    }
  }, [queryClient, latestSnapshotAt, loadedSnapshotAt])

  return history
}
