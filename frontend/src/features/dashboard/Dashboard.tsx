import { useState } from "react"
import {
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronUpIcon,
  RefreshCwIcon,
} from "lucide-react"

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
  useServiceSettings,
  useServiceStatuses,
} from "@/shared/lib/queries"
import { formatTimestamp } from "@/shared/lib/format"

const ACTIVITY_PAGE_SIZE = 5

/** Overview page: integration health and collapsible recent activity. */
export function Dashboard() {
  const { data: activity, isLoading: activityLoading } = useActivity()
  const { data: serviceStatuses, isLoading: servicesLoading } =
    useServiceStatuses()
  const { data: serviceSettings } = useServiceSettings()
  const checkNow = useCheckServiceStatuses()
  const [activityOpen, setActivityOpen] = useState(false)
  const [activityPage, setActivityPage] = useState(1)

  // Newest first, capped at the most recent 50 entries.
  const recentActivity = (activity ?? [])
    .slice()
    .sort((a, b) => b.id - a.id)
    .slice(0, 50)
  const totalActivityPages = Math.max(
    1,
    Math.ceil(recentActivity.length / ACTIVITY_PAGE_SIZE),
  )
  const currentActivityPage = Math.min(activityPage, totalActivityPages)
  const activityPageStart =
    recentActivity.length === 0
      ? 0
      : (currentActivityPage - 1) * ACTIVITY_PAGE_SIZE + 1
  const activityPageEnd = Math.min(
    currentActivityPage * ACTIVITY_PAGE_SIZE,
    recentActivity.length,
  )
  const visibleActivity = recentActivity.slice(
    activityPageStart === 0 ? 0 : activityPageStart - 1,
    activityPageEnd,
  )

  const services =
    serviceStatuses?.services ?? ({} as ServicesStatusResponse["services"])
  const lastCheck = serviceStatuses?.last_check_at

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          All-in-one ARR coordinates Trakt lists, Seer requests, Sonarr/Radarr
          searches, and download-client controls from one dashboard.
        </p>
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">
              Integrations
            </h2>
            <p className="text-sm text-muted-foreground">
              Review the current connection status for every configured service.
            </p>
          </div>
          <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center">
            <p className="text-xs text-muted-foreground sm:text-right">
              {lastCheck
                ? `Last checked ${formatTimestamp(lastCheck)}`
                : "Not checked yet"}
            </p>
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
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <IntegrationStatusCard
            label="Trakt"
            status={services["trakt"]}
            url="https://trakt.tv"
          />
          {SERVICE_TABS.map((tab) => (
            <IntegrationStatusCard
              key={tab.name}
              label={tab.label}
              status={services[tab.name]}
              url={
                tab.fields.includes("url")
                  ? serviceSettings?.[tab.name]?.url
                  : tab.homepage
              }
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
              <div className="flex flex-col gap-4">
                <ul className="divide-y">
                  {visibleActivity.map((entry) => (
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
                {totalActivityPages > 1 ? (
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-sm text-muted-foreground">
                      Showing {activityPageStart}–{activityPageEnd} of{" "}
                      {recentActivity.length}
                    </p>
                    <div className="flex items-center gap-3">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        aria-label="Previous activity page"
                        disabled={currentActivityPage <= 1}
                        onClick={() => setActivityPage(currentActivityPage - 1)}
                      >
                        <ChevronLeftIcon className="size-4" />
                        Previous
                      </Button>
                      <span className="text-sm text-muted-foreground">
                        Page {currentActivityPage} of {totalActivityPages}
                      </span>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        aria-label="Next activity page"
                        disabled={currentActivityPage >= totalActivityPages}
                        onClick={() => setActivityPage(currentActivityPage + 1)}
                      >
                        Next
                        <ChevronRightIcon className="size-4" />
                      </Button>
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </CardContent>
        ) : null}
      </Card>
    </div>
  )
}
