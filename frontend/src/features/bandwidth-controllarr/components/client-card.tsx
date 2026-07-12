import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { PauseIcon, PlayIcon } from "lucide-react"
import { Badge } from "@/shared/components/ui/badge"
import { Button } from "@/shared/components/ui/button"
import { cn } from "@/shared/lib/utils"
import type { BandwidthClient } from "@/shared/lib/api"

interface ClientCardProps {
  label: string
  online: boolean
  speed: number
  active: number
  queue: number
  paused?: boolean | null
  client: BandwidthClient
  manuallyPaused: boolean
  controlPending: boolean
  onManualPausedChange: (paused: boolean) => void
}

/**
 * Presentational card showing one download client's live statistics. Reused for
 * both qBittorrent and SABnzbd so the two client blocks stay consistent.
 */
export function ClientCard({
  label,
  online,
  speed,
  active,
  queue,
  paused,
  client,
  manuallyPaused,
  controlPending,
  onManualPausedChange,
}: ClientCardProps) {
  const actionLabel = manuallyPaused ? "Resume" : "Pause"

  return (
    <Card data-client={client} className="gap-4 py-4">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 px-4 sm:px-5">
        <CardTitle>{label}</CardTitle>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {paused != null && (
            <Badge variant={paused ? "destructive" : "secondary"}>
              {paused ? "PAUSED" : "RESUMED"}
            </Badge>
          )}
          <Badge
            variant={online ? "default" : "outline"}
            className={
              online
                ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
            }
          >
            {online ? "Online" : "Offline"}
          </Badge>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!online || controlPending}
            aria-label={`${actionLabel} ${label} downloads`}
            onClick={() => onManualPausedChange(!manuallyPaused)}
          >
            {manuallyPaused ? (
              <PlayIcon aria-hidden="true" className="size-4" />
            ) : (
              <PauseIcon aria-hidden="true" className="size-4" />
            )}
            {actionLabel}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="px-4 sm:px-5">
        <dl
          className={cn(
            "grid grid-cols-3 gap-4 text-sm",
            !online && "opacity-60",
          )}
        >
          <div>
            <dt className="text-muted-foreground">Speed</dt>
            <dd className="font-medium">{speed.toFixed(2)} MB/s</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Active</dt>
            <dd className="font-medium">{active}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Queue</dt>
            <dd className="font-medium">{queue}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  )
}
