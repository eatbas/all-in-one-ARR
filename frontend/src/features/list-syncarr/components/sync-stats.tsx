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
    description: "Sent to Seer",
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

/** Aggregate sync-engine counts, shown as stat cards in the List-Syncarr Lists tab. */
export function SyncStats() {
  const { data: status, isLoading } = useStatus()

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {STAT_CARDS.map((card) => (
        <Card key={card.key} className="gap-1 py-0">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 px-3 py-2 pb-1">
            <div className="flex items-baseline gap-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {card.title}
              </CardTitle>
              <span className="text-xl font-bold tabular-nums">
                {isLoading || status === undefined ? "–" : status.counts[card.key]}
              </span>
            </div>
            <card.icon className="size-4 shrink-0 text-muted-foreground" />
          </CardHeader>
          <CardContent className="px-3 py-1 pt-0">
            <p className="text-xs text-muted-foreground">{card.description}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
