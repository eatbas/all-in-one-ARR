import { useState, type ReactNode } from "react"
import { ChevronDownIcon } from "lucide-react"

import { Badge } from "@/shared/components/ui/badge"
import { Card, CardContent, CardHeader } from "@/shared/components/ui/card"
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
  downloadHistory: BandwidthDownloadItem[]
  queue: BandwidthQueue
}

const CLIENT_LABELS: Record<BandwidthDownloadItem["client"], string> = {
  qbittorrent: "qBittorrent",
  sabnzbd: "SABnzbd",
}

/** Queue and completed-download history for Bandwidth-Controllarr. */
export function DownloadActivityPanel({
  downloadHistory,
  queue,
}: DownloadActivityPanelProps) {
  const [isQueueOpen, setIsQueueOpen] = useState(true)
  const [isHistoryOpen, setIsHistoryOpen] = useState(false)
  const queueCount = queue.qbittorrent.length + queue.sabnzbd.length

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
            <QueueGroup label="qBittorrent" items={queue.qbittorrent} />
            <QueueGroup label="SABnzbd" items={queue.sabnzbd} />
          </div>
        )}
      </ActivitySection>

      <ActivitySection
        title="Download history"
        count={downloadHistory.length}
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
  count: number
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
                <Badge variant="secondary">{count}</Badge>
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

interface QueueGroupProps {
  label: string
  items: BandwidthDownloadItem[]
}

function QueueGroup({ label, items }: QueueGroupProps) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-medium">{label}</h3>
        <Badge variant="outline">{items.length}</Badge>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No queued downloads</p>
      ) : (
        <DownloadRows items={items} />
      )}
    </section>
  )
}

interface DownloadRowsProps {
  items: BandwidthDownloadItem[]
  mode?: "history" | "queue"
}

function DownloadRows({ items, mode = "queue" }: DownloadRowsProps) {
  return (
    <>
      <div className="flex flex-col lg:hidden" role="list">
        {items.map((item, index) => (
          <MobileDownloadRow
            key={rowKey(item, index)}
            item={item}
            mode={mode}
          />
        ))}
      </div>
      <div className="hidden lg:block">
        <DownloadTable items={items} mode={mode} />
      </div>
    </>
  )
}

function DownloadTable({ items, mode = "queue" }: DownloadRowsProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Downloader</TableHead>
          <TableHead>Name</TableHead>
          <TableHead>Progress</TableHead>
          <TableHead>Size</TableHead>
          {mode === "history" ? (
            <TableHead>Finished</TableHead>
          ) : (
            <>
              <TableHead>Speed</TableHead>
              <TableHead>ETA</TableHead>
            </>
          )}
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item, index) => (
          <DownloadRow key={rowKey(item, index)} item={item} mode={mode} />
        ))}
      </TableBody>
    </Table>
  )
}

interface DownloadRowProps {
  item: BandwidthDownloadItem
  mode?: "history" | "queue"
}

function DownloadRow({ item, mode = "queue" }: DownloadRowProps) {
  return (
    <TableRow>
      <TableCell>
        <Badge variant="outline">{CLIENT_LABELS[item.client]}</Badge>
      </TableCell>
      <TableCell>
        <DownloadName item={item} />
      </TableCell>
      <TableCell className="tabular-nums">
        {formatProgress(item.progress)}
      </TableCell>
      <TableCell className="tabular-nums">{formatSize(item)}</TableCell>
      {mode === "history" ? (
        <TableCell className="tabular-nums">
          {formatFinished(item.completed_at)}
        </TableCell>
      ) : (
        <>
          <TableCell className="tabular-nums">
            {formatSpeed(item.speed_mbps)}
          </TableCell>
          <TableCell className="tabular-nums">
            {formatEta(item.eta_seconds)}
          </TableCell>
        </>
      )}
    </TableRow>
  )
}

function MobileDownloadRow({ item, mode = "queue" }: DownloadRowProps) {
  return (
    <div
      role="listitem"
      className={cn(
        "grid min-w-0 grid-cols-2 gap-x-4 gap-y-3 border-b py-3 first:pt-0 last:border-b-0 last:pb-0",
        mode === "history" ? "sm:grid-cols-3" : "sm:grid-cols-4",
      )}
    >
      <div
        className={cn(
          "col-span-2 flex min-w-0 items-center gap-2",
          mode === "history" ? "sm:col-span-3" : "sm:col-span-4",
        )}
      >
        <Badge variant="outline" className="shrink-0">
          {CLIENT_LABELS[item.client]}
        </Badge>
        <DownloadName item={item} />
      </div>
      <MobileValue label="Progress" value={formatProgress(item.progress)} />
      <MobileValue label="Size" value={formatSize(item)} />
      {mode === "history" ? (
        <MobileValue
          label="Finished"
          value={formatFinished(item.completed_at)}
        />
      ) : (
        <>
          <MobileValue label="Speed" value={formatSpeed(item.speed_mbps)} />
          <MobileValue label="ETA" value={formatEta(item.eta_seconds)} />
        </>
      )}
    </div>
  )
}

interface MobileValueProps {
  label: string
  value: string
}

function MobileValue({ label, value }: MobileValueProps) {
  return (
    <div className="min-w-0 text-sm">
      <span className="block text-xs text-muted-foreground">{label}</span>
      <span className="block truncate font-medium tabular-nums">{value}</span>
    </div>
  )
}

function DownloadName({ item }: DownloadRowProps) {
  return (
    <span
      className="block min-w-0 max-w-[36ch] truncate font-medium"
      title={item.name}
    >
      {item.name}
    </span>
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

function formatFinished(completedAt: string | null): string {
  return completedAt === null ? "—" : formatRelativeTime(completedAt)
}
