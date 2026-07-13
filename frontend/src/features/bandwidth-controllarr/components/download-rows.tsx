import { Badge } from "@/shared/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table"
import {
  CLIENT_LABELS,
  formatEta,
  formatFinished,
  formatProgress,
  formatSize,
  formatSpeed,
  rowKey,
} from "@/features/bandwidth-controllarr/components/download-format"
import { cn } from "@/shared/lib/utils"
import type { BandwidthDownloadItem } from "@/shared/lib/api"

/** Whether the rows describe live queue entries or completed downloads. */
type DownloadRowMode = "history" | "queue"

interface DownloadRowsProps {
  items: BandwidthDownloadItem[]
  mode?: DownloadRowMode
}

/** Download rows as stacked cards on small screens and a table from `lg` up. */
export function DownloadRows({ items, mode = "queue" }: DownloadRowsProps) {
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
  mode?: DownloadRowMode
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
