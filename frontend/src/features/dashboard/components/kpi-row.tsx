import { StatBlock } from "@/shared/components/stat-block"
import type { DashboardMetric } from "@/shared/lib/api"
import { formatMetricValue } from "@/features/dashboard/lib/metric-format"

/** Number of skeleton tiles shown while the summary loads (one per KPI). */
const KPI_SKELETON_COUNT = 8

const GRID_CLASS = "grid grid-cols-2 gap-3 sm:grid-cols-4"

interface KpiRowProps {
  /** Headline figures in display order; `undefined` while loading. */
  kpis: DashboardMetric[] | undefined
}

/** Responsive grid of headline figures; skeleton tiles until data arrives. */
export function KpiRow({ kpis }: KpiRowProps) {
  if (kpis === undefined) {
    return (
      <section
        aria-label="Key figures loading"
        aria-busy="true"
        className={GRID_CLASS}
      >
        {Array.from({ length: KPI_SKELETON_COUNT }, (_, index) => (
          <div key={index} className="rounded-lg border bg-background p-4">
            <div className="h-3 w-3/5 animate-pulse rounded bg-muted" />
            <div className="mt-3 h-6 w-2/5 animate-pulse rounded bg-muted" />
          </div>
        ))}
      </section>
    )
  }

  return (
    <section aria-label="Key figures" className={GRID_CLASS}>
      {kpis.map((kpi) => (
        <StatBlock
          key={kpi.key}
          label={kpi.label}
          value={formatMetricValue(kpi.value, kpi.unit)}
          muted={kpi.value === null}
        />
      ))}
    </section>
  )
}
