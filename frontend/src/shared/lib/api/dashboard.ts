import type {
  DashboardDisk as GeneratedDashboardDisk,
  DashboardHistory as GeneratedDashboardHistory,
  DashboardHistorySeries as GeneratedDashboardHistorySeries,
  DashboardMetric as GeneratedDashboardMetric,
  DashboardSource as GeneratedDashboardSource,
  DashboardSummary as GeneratedDashboardSummary,
} from "@/shared/lib/generated"
import { request } from "@/shared/lib/api/client"

/** Cached live statistics returned by `GET /api/dashboard/summary`. */
export type DashboardSummary = GeneratedDashboardSummary

/** One module or upstream service card on the dashboard. */
export type DashboardSource = GeneratedDashboardSource

/** Closed source-state domain generated from the backend contract. */
export type DashboardSourceState = DashboardSource["state"]

/** One labelled figure; `value` is `null` when it is unavailable. */
export type DashboardMetric = GeneratedDashboardMetric

/** Free and total space of one Sonarr/Radarr mount. */
export type DashboardDisk = GeneratedDashboardDisk

/** Daily-snapshot trends returned by `GET /api/dashboard/history`. */
export type DashboardHistory = GeneratedDashboardHistory

/** One metric's daily points, oldest first. */
export type DashboardHistorySeries = GeneratedDashboardHistorySeries

/** Trend ranges (days) the history endpoint accepts. */
export type DashboardRange = DashboardHistory["days"]

/** Selectable trend ranges, in toggle order. */
export const DASHBOARD_RANGES: ReadonlyArray<DashboardRange> = [7, 30, 90]

/** Fetch the cached live statistics with a state for every source. */
export function getDashboardSummary(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/api/dashboard/summary")
}

/** Fetch the daily-snapshot trends for the last `days` days. */
export function getDashboardHistory(
  days: DashboardRange,
): Promise<DashboardHistory> {
  return request<DashboardHistory>(`/api/dashboard/history?days=${days}`)
}
