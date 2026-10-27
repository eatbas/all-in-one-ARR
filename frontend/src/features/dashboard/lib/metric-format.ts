import type { DashboardMetric } from "@/shared/lib/api"
import { formatBytes } from "@/shared/lib/format"

const COUNT_FORMAT = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 0,
})

/**
 * Format a dashboard figure for display by its unit: bytes as a binary size
 * ("1.2 TB"), speeds with one decimal ("38.6 MB/s") and counts with grouping
 * ("2,236"). An unavailable value (`null`) renders as an em dash.
 */
export function formatMetricValue(
  value: number | null,
  unit: DashboardMetric["unit"],
): string {
  if (value === null) {
    return "—"
  }
  if (unit === "bytes") {
    return formatBytes(value)
  }
  if (unit === "mbps") {
    return `${value.toFixed(1)} MB/s`
  }
  return COUNT_FORMAT.format(value)
}
