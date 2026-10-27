import type { DashboardHistory, DashboardMetric } from "@/shared/lib/api"
import { formatMetricValue } from "@/features/dashboard/lib/metric-format"

/** One chart row: the day plus each plotted series' value (`null` on a gap). */
export type TrendRow = { day: string } & Record<string, number | string | null>

/** A plotted series: its chart key and the history metrics it sums. */
export interface TrendSource {
  /** Recharts data key; must not contain "." (Recharts reads it as a path). */
  key: string
  /** History metric keys summed into this series (usually exactly one). */
  metrics: ReadonlyArray<string>
}

const DAY_MS = 86_400_000

/** Every `YYYY-MM-DD` day from `start` to `end` inclusive, oldest first. */
export function daysBetween(start: string, end: string): string[] {
  const days: string[] = []
  const last = Date.parse(`${end}T00:00:00Z`)
  for (let t = Date.parse(`${start}T00:00:00Z`); t <= last; t += DAY_MS) {
    days.push(new Date(t).toISOString().slice(0, 10))
  }
  return days
}

/**
 * Build one row per day of the history window for the given series. A day with
 * no point for any of a series' metrics is `null`, so a snapshot gap breaks the
 * line instead of being interpolated.
 */
export function buildTrendRows(
  history: DashboardHistory,
  sources: ReadonlyArray<TrendSource>,
): TrendRow[] {
  const valuesByMetric = new Map(
    history.series.map((series) => [
      series.key,
      new Map(series.points.map((point) => [point.day, point.value])),
    ]),
  )
  return daysBetween(history.start_day, history.end_day).map((day) => {
    const row: TrendRow = { day }
    for (const source of sources) {
      row[source.key] = sumForDay(valuesByMetric, source.metrics, day)
    }
    return row
  })
}

function sumForDay(
  valuesByMetric: Map<string, Map<string, number>>,
  metrics: ReadonlyArray<string>,
  day: string,
): number | null {
  const values = metrics
    .map((metric) => valuesByMetric.get(metric)?.get(day))
    .filter((value): value is number => value !== undefined)
  return values.length === 0 ? null : values.reduce((a, b) => a + b, 0)
}

/**
 * Whether `rows[index]` holds a value for `key` while neither neighbouring day
 * does. Gaps are never joined, so such an observation (the first snapshot, or
 * one between two gaps) draws no line segment and needs its own marker.
 */
export function isIsolatedPoint(
  rows: ReadonlyArray<TrendRow>,
  key: string,
  index: number,
): boolean {
  const valueAt = (position: number) => rows[position]?.[key] ?? null
  return (
    valueAt(index) !== null &&
    valueAt(index - 1) === null &&
    valueAt(index + 1) === null
  )
}

/** Whether the history holds at least one point in any series. */
export function hasTrendData(history: DashboardHistory): boolean {
  return history.series.some((series) => series.points.length > 0)
}

/** Short axis/tooltip label for a `YYYY-MM-DD` day, e.g. "26 Oct". */
export function formatDayLabel(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  })
}

/** Compact axis tick for counts: 1,500 → "1.5k". */
export function formatCompactCount(value: number): string {
  if (Math.abs(value) < 1000) {
    return String(Math.round(value))
  }
  return `${(value / 1000).toFixed(1).replace(/\.0$/, "")}k`
}

/** Tooltip heading for a chart row: the row's day label. */
export function formatTooltipDay(label: unknown): string {
  return formatDayLabel(String(label))
}

/** Tooltip value formatter for a chart whose series share one unit. */
export function trendValueFormatter(
  unit: DashboardMetric["unit"],
): (value: number) => string {
  return (value) => formatMetricValue(value, unit)
}
