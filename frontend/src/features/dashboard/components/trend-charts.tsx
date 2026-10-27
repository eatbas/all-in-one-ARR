import { useMemo, useState, type ReactNode } from "react"
import type { UseQueryResult } from "@tanstack/react-query"
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Dot,
  Line,
  XAxis,
  YAxis,
  type DotItemDotProps,
} from "recharts"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/shared/components/ui/chart"
import { Tabs, TabsList, TabsTrigger } from "@/shared/components/ui/tabs"
import {
  DASHBOARD_RANGES,
  type DashboardHistory,
  type DashboardRange,
} from "@/shared/lib/api"
import { formatBytes } from "@/shared/lib/format"
import { useDashboardHistory } from "@/shared/lib/queries"
import { cn } from "@/shared/lib/utils"
import {
  buildTrendRows,
  formatCompactCount,
  formatDayLabel,
  formatTooltipDay,
  hasTrendData,
  isIsolatedPoint,
  trendValueFormatter,
  type TrendRow,
  type TrendSource,
} from "@/features/dashboard/lib/trend-data"

const DEFAULT_RANGE: DashboardRange = 30

interface TrendSeries extends TrendSource {
  label: string
  /** Theme colour token, e.g. "var(--chart-2)". */
  colour: string
  kind: "area" | "line" | "bar"
  /** Series an order of magnitude apart use the right-hand axis. */
  axis: "left" | "right"
}

interface TrendChartDefinition {
  id: string
  title: string
  /** Accessible summary of what the chart plots. */
  description: string
  unit: "count" | "bytes"
  /** Span both columns on wide screens. */
  wide?: boolean
  series: ReadonlyArray<TrendSeries>
}

const FINDARR_TOTALS = [
  "findarr.sonarr.missing_total",
  "findarr.sonarr.upgrade_total",
  "findarr.radarr.missing_total",
  "findarr.radarr.upgrade_total",
] as const

/** The trend charts, in display order. */
const TREND_CHARTS: ReadonlyArray<TrendChartDefinition> = [
  {
    id: "sonarr",
    title: "Sonarr library",
    description: "Sonarr episodes with files and missing episodes per day",
    unit: "count",
    series: [
      {
        key: "sonarr_episodes_with_files",
        metrics: ["sonarr.episodes_with_files"],
        label: "Episodes with files",
        colour: "var(--chart-2)",
        kind: "area",
        axis: "left",
      },
      {
        key: "sonarr_episodes_missing",
        metrics: ["sonarr.episodes_missing"],
        label: "Missing episodes (right axis)",
        colour: "var(--chart-1)",
        kind: "line",
        axis: "right",
      },
    ],
  },
  {
    id: "radarr",
    title: "Radarr library",
    description: "Radarr movies with files and missing movies per day",
    unit: "count",
    series: [
      {
        key: "radarr_movies_with_files",
        metrics: ["radarr.movies_with_files"],
        label: "Movies with files",
        colour: "var(--chart-2)",
        kind: "area",
        axis: "left",
      },
      {
        key: "radarr_movies_missing",
        metrics: ["radarr.movies_missing"],
        label: "Missing movies (right axis)",
        colour: "var(--chart-1)",
        kind: "line",
        axis: "right",
      },
    ],
  },
  {
    id: "disk",
    title: "Disk free",
    description: "Free disk space per day",
    unit: "bytes",
    series: [
      {
        key: "sonarr_disk_free",
        metrics: ["sonarr.disk_free_bytes"],
        label: "Sonarr",
        colour: "var(--chart-3)",
        kind: "line",
        axis: "left",
      },
      {
        key: "radarr_disk_free",
        metrics: ["radarr.disk_free_bytes"],
        label: "Radarr",
        colour: "var(--chart-1)",
        kind: "line",
        axis: "left",
      },
    ],
  },
  {
    id: "requests",
    title: "Requests",
    description: "Seer requests by status per day",
    unit: "count",
    series: [
      {
        key: "seer_pending",
        metrics: ["seer.requests_pending"],
        label: "Pending",
        colour: "var(--chart-1)",
        kind: "line",
        axis: "left",
      },
      {
        key: "seer_approved",
        metrics: ["seer.requests_approved"],
        label: "Approved",
        colour: "var(--chart-2)",
        kind: "line",
        axis: "left",
      },
      {
        key: "seer_available",
        metrics: ["seer.requests_available"],
        label: "Available (right axis)",
        colour: "var(--chart-3)",
        kind: "line",
        axis: "right",
      },
    ],
  },
  {
    id: "modules",
    title: "Module activity",
    description: "Findarr searches per day and Languagarr non-compliant files",
    unit: "count",
    wide: true,
    series: [
      {
        key: "findarr_searches",
        metrics: FINDARR_TOTALS,
        label: "Findarr searches per day",
        colour: "var(--chart-4)",
        kind: "bar",
        axis: "left",
      },
      {
        key: "languagarr_non_compliant",
        metrics: ["languagarr.non_compliant"],
        label: "Languagarr non-compliant files",
        colour: "var(--chart-1)",
        kind: "line",
        axis: "left",
      },
    ],
  },
]

interface TrendChartsProps {
  /**
   * The summary's newest snapshot version (`undefined` while it is unknown);
   * a change refreshes the trends (see `useDashboardHistory`).
   */
  latestSnapshotAt?: string | null
}

/**
 * Daily-snapshot trends with a 7/30/90-day toggle. Loaded lazily from the
 * Dashboard so Recharts stays out of the initial bundle.
 */
export function TrendCharts({ latestSnapshotAt }: TrendChartsProps) {
  const [range, setRange] = useState<DashboardRange>(DEFAULT_RANGE)
  const history = useDashboardHistory(range, latestSnapshotAt)

  return (
    <Card aria-labelledby="trends-title">
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <CardTitle id="trends-title">Trends</CardTitle>
          <CardDescription>Daily snapshots taken at 23:55.</CardDescription>
        </div>
        <Tabs
          value={String(range)}
          // Radix only emits the trigger values below, all valid ranges.
          onValueChange={(value) => setRange(Number(value) as DashboardRange)}
        >
          <TabsList aria-label="Trend range">
            {DASHBOARD_RANGES.map((days) => (
              <TabsTrigger key={days} value={String(days)}>
                {days} days
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </CardHeader>
      <CardContent>
        <TrendBody history={history} />
      </CardContent>
    </Card>
  )
}

function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">
      {children}
    </p>
  )
}

function TrendBody({ history }: { history: UseQueryResult<DashboardHistory> }) {
  if (history.isError) {
    return (
      <EmptyState>Could not load trends: {history.error.message}</EmptyState>
    )
  }
  if (history.data === undefined) {
    return <EmptyState>Loading trends…</EmptyState>
  }
  if (!hasTrendData(history.data)) {
    return (
      <EmptyState>
        Collecting data — trends appear after the first daily snapshot
      </EmptyState>
    )
  }
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {TREND_CHARTS.map((chart) => (
        <TrendChart key={chart.id} chart={chart} history={history.data} />
      ))}
    </div>
  )
}

function TrendChart({
  chart,
  history,
}: {
  chart: TrendChartDefinition
  history: DashboardHistory
}) {
  const rows = useMemo(
    () => buildTrendRows(history, chart.series),
    [history, chart],
  )
  const config: ChartConfig = Object.fromEntries(
    chart.series.map((series) => [
      series.key,
      { label: series.label, color: series.colour },
    ]),
  )
  const tickFormatter =
    chart.unit === "bytes" ? formatBytes : formatCompactCount
  const hasRightAxis = chart.series.some((series) => series.axis === "right")

  return (
    <figure
      className={cn("m-0 rounded-lg border p-4", chart.wide && "lg:col-span-2")}
    >
      <figcaption className="text-sm font-medium">{chart.title}</figcaption>
      <ChartContainer
        config={config}
        role="img"
        aria-label={chart.description}
        className="mt-2 aspect-auto h-[200px] w-full"
      >
        <ComposedChart data={rows} margin={{ top: 8, left: 0, right: 0 }}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" />
          <XAxis
            dataKey="day"
            tickFormatter={formatDayLabel}
            tickLine={false}
            axisLine={false}
            minTickGap={24}
          />
          <YAxis
            yAxisId="left"
            tickFormatter={tickFormatter}
            tickLine={false}
            axisLine={false}
            width={56}
          />
          {hasRightAxis ? (
            <YAxis
              yAxisId="right"
              orientation="right"
              tickFormatter={tickFormatter}
              tickLine={false}
              axisLine={false}
              width={56}
            />
          ) : null}
          <ChartTooltip
            content={
              <ChartTooltipContent
                labelFormatter={formatTooltipDay}
                valueFormatter={trendValueFormatter(chart.unit)}
              />
            }
          />
          {chart.series.map((series) => renderSeries(series, rows))}
        </ComposedChart>
      </ChartContainer>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {chart.series.map((series) => (
          <li key={series.key} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-2 rounded-[2px]"
              style={{ background: series.colour }}
            />
            {series.label}
          </li>
        ))}
      </ul>
    </figure>
  )
}

/**
 * Dot renderer for an area or line series that marks only isolated
 * observations (see `isIsolatedPoint`); joined points stay unmarked. `Dot`
 * itself renders nothing without coordinates.
 */
function isolatedDot(rows: ReadonlyArray<TrendRow>, series: TrendSeries) {
  return function renderIsolatedDot({ cx, cy, index }: DotItemDotProps) {
    if (!isIsolatedPoint(rows, series.key, index)) {
      return null
    }
    return (
      <Dot
        cx={cx}
        cy={cy}
        r={3}
        fill={`var(--color-${series.key})`}
        className="trend-isolated-dot"
      />
    )
  }
}

/**
 * Render one series; gaps (`null`) are never joined, and an observation with
 * no neighbour on either side is drawn as a dot.
 */
function renderSeries(series: TrendSeries, rows: ReadonlyArray<TrendRow>) {
  const colour = `var(--color-${series.key})`
  const shared = {
    dataKey: series.key,
    name: series.label,
    yAxisId: series.axis,
    isAnimationActive: false,
  }
  if (series.kind === "bar") {
    return <Bar key={series.key} {...shared} fill={colour} radius={2} />
  }
  if (series.kind === "area") {
    return (
      <Area
        key={series.key}
        {...shared}
        type="monotone"
        stroke={colour}
        strokeWidth={2}
        fill={colour}
        fillOpacity={0.15}
        connectNulls={false}
        dot={isolatedDot(rows, series)}
      />
    )
  }
  return (
    <Line
      key={series.key}
      {...shared}
      type="monotone"
      stroke={colour}
      strokeWidth={2}
      connectNulls={false}
      dot={isolatedDot(rows, series)}
    />
  )
}
