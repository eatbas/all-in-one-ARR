import { useState } from "react"
import { ChevronDownIcon } from "lucide-react"

import { Badge } from "@/shared/components/ui/badge"
import { Button } from "@/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table"
import { formatBytes, formatRelativeTime } from "@/shared/lib/format"
import { cn } from "@/shared/lib/utils"
import type { BandwidthDownloadItem, BandwidthQueue } from "@/shared/lib/api"

interface DownloadActivityPanelProps {
  recentDownloads: BandwidthDownloadItem[]
  queue: BandwidthQueue
}

const CLIENT_LABELS: Record<BandwidthDownloadItem["client"], string> = {
  qbittorrent: "qBittorrent",
  sabnzbd: "SABnzbd",
}

/** Recent downloads and current queue display for Bandwidth-Controllarr. */
export function DownloadActivityPanel({
  recentDownloads,
  queue,
}: DownloadActivityPanelProps) {
  const [isQueueOpen, setIsQueueOpen] = useState(false)
  const queueCount = queue.qbittorrent.length + queue.sabnzbd.length

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>Recent downloads</CardTitle>
          <Badge variant="secondary">{recentDownloads.length}</Badge>
        </CardHeader>
        <CardContent>
          {recentDownloads.length === 0 ? (
            <p className="text-sm text-muted-foreground">No recent downloads</p>
          ) : (
            <DownloadTable
              items={recentDownloads}
              timestampLabel="Finished"
              emptyText="No recent downloads"
            />
          )}
        </CardContent>
      </Card>

      <Collapsible open={isQueueOpen} onOpenChange={setIsQueueOpen}>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <CardTitle>Queue</CardTitle>
              <Badge variant="secondary">{queueCount}</Badge>
            </div>
            <CollapsibleTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={
                  isQueueOpen
                    ? "Collapse downloader queue"
                    : "Expand downloader queue"
                }
              >
                <ChevronDownIcon
                  aria-hidden="true"
                  className={cn(
                    "size-4 transition-transform",
                    isQueueOpen && "rotate-180",
                  )}
                />
              </Button>
            </CollapsibleTrigger>
          </CardHeader>
          <CollapsibleContent>
            <CardContent className="flex flex-col gap-6">
              {queueCount === 0 ? (
                <p className="text-sm text-muted-foreground">Queue is empty</p>
              ) : (
                <>
                  <QueueGroup label="qBittorrent" items={queue.qbittorrent} />
                  <QueueGroup label="SABnzbd" items={queue.sabnzbd} />
                </>
              )}
            </CardContent>
          </CollapsibleContent>
        </Card>
      </Collapsible>
    </div>
  )
}

interface QueueGroupProps {
  label: string
  items: BandwidthDownloadItem[]
}

function QueueGroup({ label, items }: QueueGroupProps) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-medium">{label}</h3>
        <Badge variant="outline">{items.length}</Badge>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No queued downloads</p>
      ) : (
        <DownloadTable
          items={items}
          timestampLabel="Added"
          emptyText="Queue is empty"
        />
      )}
    </section>
  )
}

interface DownloadTableProps {
  items: BandwidthDownloadItem[]
  timestampLabel: string
  emptyText: string
}

function DownloadTable({
  items,
  timestampLabel,
  emptyText,
}: DownloadTableProps) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">{emptyText}</p>
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Downloader</TableHead>
          <TableHead>Name</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Progress</TableHead>
          <TableHead>Size</TableHead>
          <TableHead>Speed</TableHead>
          <TableHead>ETA</TableHead>
          <TableHead>{timestampLabel}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item, index) => (
          <DownloadRow key={rowKey(item, index)} item={item} />
        ))}
      </TableBody>
    </Table>
  )
}

interface DownloadRowProps {
  item: BandwidthDownloadItem
}

function DownloadRow({ item }: DownloadRowProps) {
  return (
    <TableRow>
      <TableCell>
        <Badge variant="outline">{CLIENT_LABELS[item.client]}</Badge>
      </TableCell>
      <TableCell>
        <span
          className="block max-w-[36ch] truncate font-medium"
          title={item.name}
        >
          {item.name}
        </span>
      </TableCell>
      <TableCell>{item.status}</TableCell>
      <TableCell className="tabular-nums">
        {formatProgress(item.progress)}
      </TableCell>
      <TableCell className="tabular-nums">{formatSize(item)}</TableCell>
      <TableCell className="tabular-nums">
        {formatSpeed(item.speed_mbps)}
      </TableCell>
      <TableCell className="tabular-nums">
        {formatEta(item.eta_seconds)}
      </TableCell>
      <TableCell className="whitespace-nowrap text-muted-foreground">
        {formatActivityTime(item)}
      </TableCell>
    </TableRow>
  )
}

function rowKey(item: BandwidthDownloadItem, index: number): string {
  return `${item.client}-${item.id}-${item.completed_at ?? item.added_at ?? index}`
}

function formatProgress(progress: number | null): string {
  return progress === null
    ? "—"
    : `${progress.toFixed(progress % 1 === 0 ? 0 : 1)}%`
}

function formatSize(item: BandwidthDownloadItem): string {
  if (item.size_label !== null) {
    return item.size_label
  }
  return item.size_bytes === null ? "—" : formatBytes(item.size_bytes)
}

function formatSpeed(speed: number | null): string {
  return speed === null ? "—" : `${speed.toFixed(2)} MB/s`
}

function formatEta(seconds: number | null): string {
  if (seconds === null) {
    return "—"
  }
  if (seconds < 60) {
    return `${seconds}s`
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)}m`
  }
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}m`
}

function formatActivityTime(item: BandwidthDownloadItem): string {
  const timestamp = item.completed_at ?? item.added_at
  return timestamp === null ? "—" : formatRelativeTime(timestamp)
}
