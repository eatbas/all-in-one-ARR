import {
  CheckCircle2Icon,
  DownloadIcon,
  SendIcon,
  Trash2Icon,
  type LucideIcon,
} from "lucide-react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { useActivity, useStatus } from "@/lib/queries"
import type { StatusCounts } from "@/lib/api"

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

/** Format an ISO timestamp for the activity feed; falls back to the raw value. */
function formatTimestamp(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return iso
  }
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  })
}

/** Overview page: four stat cards plus a recent-activity feed. */
export function Dashboard() {
  const { data: status, isLoading: statusLoading } = useStatus()
  const { data: activity, isLoading: activityLoading } = useActivity()

  // Newest first, capped at the most recent 50 entries.
  const recentActivity = (activity ?? [])
    .slice()
    .sort((a, b) => b.id - a.id)
    .slice(0, 50)

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

      <Card>
        <CardHeader>
          <CardTitle>Recent activity</CardTitle>
          <CardDescription>
            The 50 most recent actions taken by the sync engine.
          </CardDescription>
        </CardHeader>
        <CardContent>
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
      </Card>
    </div>
  )
}
