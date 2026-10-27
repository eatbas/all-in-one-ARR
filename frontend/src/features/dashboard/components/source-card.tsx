import { ArrowUpRightIcon } from "lucide-react"
import { Link } from "react-router-dom"

import { Badge } from "@/shared/components/ui/badge"
import { Card, CardContent, CardHeader } from "@/shared/components/ui/card"
import type { DashboardSource, DashboardSourceState } from "@/shared/lib/api"
import { formatRelativeTime } from "@/shared/lib/format"
import { cn } from "@/shared/lib/utils"
import { formatMetricValue } from "@/features/dashboard/lib/metric-format"

type BadgeVariant = "destructive" | "outline" | "secondary"

/** Badge shown beside the title for each non-`ok` state. */
const STATE_BADGES: Record<
  DashboardSourceState,
  { label: string; variant: BadgeVariant } | null
> = {
  ok: null,
  offline: { label: "Offline", variant: "destructive" },
  not_configured: { label: "Not configured", variant: "outline" },
  disabled: { label: "Disabled", variant: "secondary" },
}

interface SourceCardProps {
  source: DashboardSource
}

/**
 * Read-only statistics card for one module or upstream service. The title links
 * to the source's own page (or Settings); the state badge, any explanatory line
 * and the metric list follow the source's state. It has no controls.
 */
export function SourceCard({ source }: SourceCardProps) {
  const badge = STATE_BADGES[source.state]
  const disabled = source.state === "disabled"

  return (
    <Card className={cn("gap-4 py-5", disabled && "bg-muted/50")}>
      <CardHeader
        className={cn(
          "flex flex-row items-center justify-between gap-2 px-5",
          disabled && "opacity-65",
        )}
      >
        <Link
          to={source.link}
          className="inline-flex items-center gap-1.5 leading-none font-semibold underline-offset-4 hover:underline"
        >
          {source.label}
          <ArrowUpRightIcon
            aria-hidden="true"
            className="size-3.5 text-muted-foreground"
          />
        </Link>
        {badge ? <Badge variant={badge.variant}>{badge.label}</Badge> : null}
      </CardHeader>
      <CardContent className={cn("px-5", disabled && "opacity-65")}>
        <SourceBody source={source} />
      </CardContent>
    </Card>
  )
}

function SourceBody({ source }: SourceCardProps) {
  if (source.state === "not_configured") {
    return (
      <p className="text-sm text-muted-foreground">
        {source.detail ?? "This service is not connected yet."}{" "}
        <Link
          to="/settings"
          className="font-medium text-foreground underline underline-offset-4"
        >
          Set up in Settings
        </Link>
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {source.state === "offline" ? (
        <OfflineLine source={source} />
      ) : (
        <StatusLine source={source} />
      )}
      {source.metrics.length > 0 ? <MetricList source={source} /> : null}
    </div>
  )
}

function OfflineLine({ source }: SourceCardProps) {
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
      <span>
        {source.stale_since
          ? `Stale since ${formatRelativeTime(source.stale_since)}`
          : "No earlier snapshot"}
      </span>
      {source.detail ? (
        <>
          <span aria-hidden="true">·</span>
          <span>{source.detail}</span>
        </>
      ) : null}
    </p>
  )
}

/**
 * The explanatory line for an `ok` or `disabled` source: its detail, else (when
 * it reports no figures) when its data last refreshed, or why it has none.
 */
function StatusLine({ source }: SourceCardProps) {
  const text = statusText(source)
  return text ? <p className="text-sm text-muted-foreground">{text}</p> : null
}

function statusText(source: DashboardSource): string | null {
  if (source.detail) {
    return source.detail
  }
  if (source.metrics.length > 0) {
    return null
  }
  if (source.state === "disabled") {
    return "No statistics while the module is disabled."
  }
  return source.updated_at
    ? `Last refreshed ${formatRelativeTime(source.updated_at)}`
    : "Not refreshed yet"
}

function MetricList({ source }: SourceCardProps) {
  return (
    <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-sm">
      {source.metrics.map((metric) => (
        <div key={metric.key} className="contents">
          <dt className="text-muted-foreground">{metric.label}</dt>
          <dd className="text-right font-medium tabular-nums">
            {formatMetricValue(metric.value, metric.unit)}
          </dd>
        </div>
      ))}
    </dl>
  )
}
