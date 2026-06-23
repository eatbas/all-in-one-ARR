import { useState } from "react"
import {
  CheckCircle2Icon,
  ChevronDownIcon,
  ChevronUpIcon,
  DownloadIcon,
  RefreshCwIcon,
  SendIcon,
  Trash2Icon,
  type LucideIcon,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { IntegrationStatusCard } from "@/components/integration-status-card"
import { SERVICE_TABS } from "@/lib/services"
import type { ServicesStatusResponse, StatusCounts } from "@/lib/api"
import {
  useActivity,
  useCheckServiceStatuses,
  useServiceStatuses,
  useStatus,
} from "@/lib/queries"
import { formatTimestamp } from "@/lib/format"

interface StatCard {
  key: keyof StatusCounts
  title: string
  description: string
  icon: LucideIcon
}

const STAT_CARDS: ReadonlyArray<StatCard> = [
  {
    key: "synced",
    title: "Synced",
    description: "Mirrored from Trakt",
    icon: SendIcon,
  },
  {
    key: "requested",
    title: "Requested",
    description: "Sent to Jellyseerr",
    icon: DownloadIcon,
  },
  {
    key: "available",
    title: "Available",
    description: "Imported and ready",
    icon: CheckCircle2Icon,
  },
  {
    key: "removed",
    title: "Removed",
    description: "Cleared from the list",
    icon: Trash2Icon,
  },
]

/** Overview page: stat cards, integration health, and collapsible recent activity. */
export function Dashboard() {
  const { data: status, isLoading: statusLoading } = useStatus()
  const { data: activity, isLoading: activityLoading } = useActivity()
  const { data: serviceStatuses, isLoading: servicesLoading } =
    useServiceStatuses()
  const checkNow = useCheckServiceStatuses()
  const [activityOpen, setActivityOpen] = useState(true)

  // Newest first, capped at the most recent 50 entries.
  const recentActivity = (activity ?? [])
    .slice()
    .sort((a, b) => b.id - a.id)
    .slice(0, 50)

  const services =
    serviceStatuses?.services ??
    ({} as ServicesStatusResponse["services"])
  const lastCheck = serviceStatuses?.last_check_at

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STAT_CARDS.map((card) => (
          <Card key={card.key}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {card.title}
              </CardTitle>
              <card.icon className="size-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold tabular-nums">
                {statusLoading || status === undefined
                  ? "–"
                  : status.counts[card.key]}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {card.description}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">
              Integrations
            </h2>
            <p className="text-xs text-muted-foreground">
              {lastCheck
                ? `Last checked ${formatTimestamp(lastCheck)}`
                : "Not checked yet"}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => checkNow.mutate()}
            disabled={checkNow.isPending || servicesLoading}
          >
            <RefreshCwIcon
              className={cn(
                "mr-2 size-4",
                checkNow.isPending && "animate-spin",
              )}
            />
            Check now
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <IntegrationStatusCard
            name="trakt"
            label="Trakt"
            status={services["trakt"]}
            compact
          />
          {SERVICE_TABS.map((tab) => (
            <IntegrationStatusCard
              key={tab.name}
              name={tab.name}
              label={tab.label}
              status={services[tab.name]}
              compact
            />
          ))}
        </div>
      </div>

      <Card>
        <CardHeader
          className="cursor-pointer pb-3"
          role="button"
          tabIndex={0}
          aria-expanded={activityOpen}
          aria-controls="activity-content"
          onClick={() => setActivityOpen((open) => !open)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault()
              setActivityOpen((open) => !open)
            }
          }}
        >
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle>Recent activity</CardTitle>
              <CardDescription>
                The 50 most recent actions taken by the sync engine.
              </CardDescription>
            </div>
            <span className="inline-flex items-center text-sm font-medium text-muted-foreground">
              {activityOpen ? (
                <>
                  <ChevronUpIcon className="mr-2 size-4" /> Hide
                </>
              ) : (
                <>
                  <ChevronDownIcon className="mr-2 size-4" /> Show
                </>
              )}
            </span>
          </div>
        </CardHeader>
        {activityOpen ? (
          <CardContent id="activity-content">
            {activityLoading ? (
              <p className="text-sm text-muted-foreground">Loading activity…</p>
            ) : recentActivity.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No activity recorded yet.
              </p>
            ) : (
              <ul className="divide-y">
                {recentActivity.map((entry) => (
                  <li
                    key={entry.id}
                    className="flex items-start justify-between gap-4 py-3 first:pt-0 last:pb-0"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{entry.action}</p>
                      <p className="truncate text-sm text-muted-foreground">
                        {entry.detail}
                      </p>
                    </div>
                    <time
                      dateTime={entry.ts}
                      className="shrink-0 text-xs text-muted-foreground"
                    >
                      {formatTimestamp(entry.ts)}
                    </time>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        ) : null}
      </Card>
    </div>
  )
}
