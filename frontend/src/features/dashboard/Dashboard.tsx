import { useState } from "react"
import { ChevronDownIcon, ChevronUpIcon, RefreshCwIcon } from "lucide-react"

import { Button } from "@/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { cn } from "@/shared/lib/utils"
import { IntegrationStatusCard } from "@/features/dashboard/components/integration-status-card"
import { SERVICE_TABS } from "@/shared/lib/services"
import type { ServicesStatusResponse } from "@/shared/lib/api"
import {
  useActivity,
  useCheckServiceStatuses,
  useServiceStatuses,
} from "@/shared/lib/queries"
import { formatTimestamp } from "@/shared/lib/format"

/** Overview page: integration health and collapsible recent activity. */
export function Dashboard() {
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
                Recent meaningful app activity from the last 15 days.
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
