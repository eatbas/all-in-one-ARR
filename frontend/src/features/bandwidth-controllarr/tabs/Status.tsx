import { Badge } from "@/shared/components/ui/badge"
import { Card, CardContent } from "@/shared/components/ui/card"
import { SettingsHelp } from "@/shared/components/settings-help"
import { Switch } from "@/shared/components/ui/switch"
import { ClientCard } from "@/features/bandwidth-controllarr/components/client-card"
import { DownloadActivityPanel } from "@/features/bandwidth-controllarr/components/download-activity-panel"
import {
  useBandwidthStatus,
  useSetBandwidthClientPaused,
  useUpdateBandwidthSettings,
} from "@/shared/lib/queries"
import { formatTimestamp } from "@/shared/lib/format"
import { cn } from "@/shared/lib/utils"
import type { BandwidthQueue } from "@/shared/lib/api"

/** Queue shown before the first status response arrives. */
const EMPTY_QUEUE: BandwidthQueue = {
  qbittorrent: { items: [], total: 0 },
  sabnzbd: { items: [], total: 0 },
}

/**
 * Bandwidth-Controllarr Status tab: shows the system-status banner, the master
 * enable/disable switch, and live cards for both download clients.
 */
export function Status() {
  const { data: status } = useBandwidthStatus()
  const updateSettings = useUpdateBandwidthSettings()
  const updateClient = useSetBandwidthClientPaused()

  const enabled = status?.enabled ?? false
  const statusText = status?.status ?? "Monitoring only"
  const isActive = status?.status.includes("Active torrents") ?? false
  const qb = status?.qbittorrent
  const sab = status?.sabnzbd
  const downloadHistory = status?.download_history ?? []
  const queue = status?.queue ?? EMPTY_QUEUE
  const controlLabel = enabled
    ? status?.tracking_suspended
      ? "Suspended"
      : "Enabled"
    : "Disabled"
  const badgeLabel = enabled ? statusText : `${statusText} (Disabled)`

  return (
    <div className="flex flex-col gap-4">
      <Card className={cn("gap-4 py-4", isActive && "border-destructive")}>
        <CardContent className="flex flex-col gap-4 px-4 sm:flex-row sm:items-center sm:px-5">
          <div className="min-w-0">
            <p className="font-medium">System Status</p>
            <p className="text-sm text-muted-foreground">
              {status?.last_run_at
                ? `Last check: ${formatTimestamp(status.last_run_at)}`
                : "Waiting for first check…"}
            </p>
          </div>
          <div className="flex items-center gap-3 sm:ml-8">
            <Switch
              aria-label="Enable bandwidth control"
              checked={enabled}
              disabled={updateSettings.isPending}
              onCheckedChange={(checked) =>
                updateSettings.mutate({ enabled: checked })
              }
            />
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-medium">{controlLabel}</span>
              <SettingsHelp label="Enable bandwidth control">
                Allows SABnzbd to pause while qBittorrent has active torrents
                and resume when idle.
              </SettingsHelp>
            </div>
          </div>
          <Badge
            variant={isActive ? "destructive" : "default"}
            className={cn(
              "w-fit max-w-full px-4 py-2 text-sm font-semibold sm:ml-auto",
              !isActive &&
                "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
            )}
          >
            {badgeLabel}
          </Badge>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <ClientCard
          label="qBittorrent"
          client="qbittorrent"
          online={qb?.online ?? false}
          speed={qb?.speed_mbps ?? 0}
          active={qb?.active_downloads ?? 0}
          queue={qb?.queue_size ?? 0}
          manuallyPaused={
            status?.manual_paused_clients.includes("qbittorrent") ?? false
          }
          controlPending={updateClient.isPending}
          onManualPausedChange={(paused) =>
            updateClient.mutate({ client: "qbittorrent", paused })
          }
        />
        <ClientCard
          label="SABnzbd"
          client="sabnzbd"
          online={sab?.online ?? false}
          speed={sab?.speed_mbps ?? 0}
          active={sab?.active_downloads ?? 0}
          queue={sab?.queue_size ?? 0}
          paused={sab?.paused}
          manuallyPaused={
            status?.manual_paused_clients.includes("sabnzbd") ?? false
          }
          controlPending={updateClient.isPending}
          onManualPausedChange={(paused) =>
            updateClient.mutate({ client: "sabnzbd", paused })
          }
        />
      </div>

      <DownloadActivityPanel downloadHistory={downloadHistory} queue={queue} />
    </div>
  )
}
