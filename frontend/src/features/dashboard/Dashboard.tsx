import { lazy, Suspense } from "react"

import { Card, CardContent } from "@/shared/components/ui/card"
import { useDashboardSummary } from "@/shared/lib/queries"
import { ActivityFeed } from "@/features/dashboard/components/activity-feed"
import { DiskSpaceCard } from "@/features/dashboard/components/disk-space-card"
import { IntegrationsSection } from "@/features/dashboard/components/integrations-section"
import { KpiRow } from "@/features/dashboard/components/kpi-row"
import { SourceCard } from "@/features/dashboard/components/source-card"

// Recharts is only needed for the trend charts; load it on demand.
const TrendCharts = lazy(() =>
  import("@/features/dashboard/components/trend-charts").then((module) => ({
    default: module.TrendCharts,
  })),
)

/** Read-only statistics dashboard: integrations, figures, trends, activity. */
export function Dashboard() {
  const summary = useDashboardSummary()

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Statistics, trends and health for every app All-in-One ARR manages.
        </p>
      </div>

      <IntegrationsSection />

      {summary.isError ? (
        <Card role="alert" className="border-destructive/50">
          <CardContent className="flex flex-col gap-1">
            <p className="text-sm font-semibold">
              Could not load dashboard statistics
            </p>
            <p className="text-sm text-muted-foreground">
              {summary.error.message}
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          <KpiRow kpis={summary.data?.kpis} />
          {summary.data ? (
            <>
              <section
                aria-label="Apps"
                className="grid gap-4 md:grid-cols-2 xl:grid-cols-3"
              >
                {summary.data.sources.map((source) => (
                  <SourceCard key={source.key} source={source} />
                ))}
              </section>
              <DiskSpaceCard disks={summary.data.disks} />
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Loading statistics…</p>
          )}
        </>
      )}

      <Suspense
        fallback={
          <p className="text-sm text-muted-foreground">Loading trends…</p>
        }
      >
        <TrendCharts latestSnapshotAt={summary.data?.latest_snapshot_at} />
      </Suspense>

      <ActivityFeed />
    </div>
  )
}
