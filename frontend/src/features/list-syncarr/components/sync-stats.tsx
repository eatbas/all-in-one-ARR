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
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { useStatus } from "@/shared/lib/queries"
import type { StatusCounts } from "@/shared/lib/api"

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

/** Aggregate sync-engine counts, shown as stat cards atop the List-Syncarr page. */
export function SyncStats() {
  const { data: status, isLoading } = useStatus()

  return (
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
              {isLoading || status === undefined ? "–" : status.counts[card.key]}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {card.description}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
