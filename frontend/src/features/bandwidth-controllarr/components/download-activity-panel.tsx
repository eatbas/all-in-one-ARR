import { useState, type ReactNode } from "react"
import { ChevronDownIcon } from "lucide-react"

import { Badge } from "@/shared/components/ui/badge"
import { Card, CardContent, CardHeader } from "@/shared/components/ui/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible"
import { DownloadRows } from "@/features/bandwidth-controllarr/components/download-rows"
import { QueueGroup } from "@/features/bandwidth-controllarr/components/queue-group"
import { cn } from "@/shared/lib/utils"
import type { BandwidthDownloadItem, BandwidthQueue } from "@/shared/lib/api"

interface DownloadActivityPanelProps {
  downloadHistory: BandwidthDownloadItem[]
  queue: BandwidthQueue
}

/** Queue and completed-download history for Bandwidth-Controllarr. */
export function DownloadActivityPanel({
  downloadHistory,
  queue,
}: DownloadActivityPanelProps) {
  const [isQueueOpen, setIsQueueOpen] = useState(true)
  const [isHistoryOpen, setIsHistoryOpen] = useState(false)
  // Cumulative: the whole queue across both downloaders, not the rows on screen.
  const queueCount = queue.qbittorrent.total + queue.sabnzbd.total

  return (
    <div className="flex flex-col gap-4">
      <ActivitySection
        title="Queue"
        count={queueCount}
        open={isQueueOpen}
        onOpenChange={setIsQueueOpen}
        accessibleName="downloader queue"
      >
        {queueCount === 0 ? (
          <p className="text-sm text-muted-foreground">Queue is empty</p>
        ) : (
          <div className="flex flex-col gap-5">
            <QueueGroup label="qBittorrent" group={queue.qbittorrent} />
            <QueueGroup label="SABnzbd" group={queue.sabnzbd} />
          </div>
        )}
      </ActivitySection>

      {/* The history is a fixed window of the most recent completions, so it
          carries no count badge — the number would never be news. */}
      <ActivitySection
        title="Download history"
        open={isHistoryOpen}
        onOpenChange={setIsHistoryOpen}
        accessibleName="download history"
      >
        {downloadHistory.length === 0 ? (
          <p className="text-sm text-muted-foreground">No download history</p>
        ) : (
          <DownloadRows items={downloadHistory} mode="history" />
        )}
      </ActivitySection>
    </div>
  )
}

interface ActivitySectionProps {
  title: string
  /** Omit to render the section without a count badge. */
  count?: number
  open: boolean
  onOpenChange: (open: boolean) => void
  accessibleName: string
  children: ReactNode
}

function ActivitySection({
  title,
  count,
  open,
  onOpenChange,
  accessibleName,
  children,
}: ActivitySectionProps) {
  return (
    <Collapsible open={open} onOpenChange={onOpenChange}>
      <Card className="gap-0 overflow-hidden py-0">
        <CardHeader className="p-0">
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex w-full items-center justify-between gap-3 px-4 py-4 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset sm:px-5"
              aria-label={`${open ? "Collapse" : "Expand"} ${accessibleName}`}
            >
              <span className="flex min-w-0 items-center gap-3">
                <span className="truncate text-base font-semibold">
                  {title}
                </span>
                {count !== undefined && (
                  <Badge variant="secondary">{count}</Badge>
                )}
              </span>
              <ChevronDownIcon
                aria-hidden="true"
                className={cn(
                  "size-4 shrink-0 transition-transform",
                  open && "rotate-180",
                )}
              />
            </button>
          </CollapsibleTrigger>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className="px-4 pb-4 sm:px-5 sm:pb-5">
            {children}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}
