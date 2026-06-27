import { ActivityIcon, SettingsIcon } from "lucide-react"

import { Badge } from "@/shared/components/ui/badge"
import { Card, CardContent } from "@/shared/components/ui/card"
import { Switch } from "@/shared/components/ui/switch"
import { ClientCard } from "@/features/bandwidth-controllarr/components/client-card"
import {
  useBandwidthStatus,
  useUpdateBandwidthSettings,
} from "@/shared/lib/queries"
import { formatTimestamp } from "@/shared/lib/format"
import { cn } from "@/shared/lib/utils"

/**
 * Bandwidth-Controllarr Status tab: shows the system-status banner, the master
 * enable/disable switch, and live cards for both download clients.
 */
export function Status() {
  const { data: status } = useBandwidthStatus()
  const updateSettings = useUpdateBandwidthSettings()

  const enabled = status?.enabled ?? false
  const isActive = status?.status.includes("Active torrents") ?? false
  const qb = status?.qbittorrent
  const sab = status?.sabnzbd

  return (
    <div className="flex flex-col gap-6">
      <Card className={isActive ? "border-destructive" : undefined}>
        <CardContent className="flex items-center justify-between gap-4 py-6">
          <div className="flex items-center gap-3">
            <ActivityIcon
              className={cn(
                "size-5",
                isActive ? "text-destructive" : "text-emerald-500",
              )}
            />
            <div>
              <p className="font-medium">
                {status?.status ?? "Monitoring only"}
              </p>
              <p className="text-sm text-muted-foreground">
                {status?.last_run_at
                  ? `Last check: ${formatTimestamp(status.last_run_at)}`
                  : "Waiting for first check…"}
              </p>
            </div>
          </div>
          <Badge variant={isActive ? "destructive" : "default"}>
            {isActive ? "Control active" : "Idle"}
          </Badge>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between gap-4 rounded-xl border bg-card p-6 shadow-sm">
        <div>
          <p className="font-medium">Bandwidth control</p>
          <p className="text-sm text-muted-foreground">
            When on, SABnzbd pauses while qBittorrent has active torrents and
            resumes when they finish.{" "}
            <a
              href="/settings"
              className="inline-flex items-center gap-1 text-primary hover:underline"
            >
              Configure connections in Settings
              <SettingsIcon className="size-3" />
            </a>
          </p>
        </div>
        <Switch
          aria-label="Enable bandwidth control"
          checked={enabled}
          disabled={updateSettings.isPending}
          onCheckedChange={(checked) =>
            updateSettings.mutate({ enabled: checked })
          }
        />
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <ClientCard
          label="qBittorrent"
          online={qb?.online ?? false}
          speed={qb?.speed_mbps ?? 0}
          active={qb?.active_downloads ?? 0}
          queue={qb?.queue_size ?? 0}
        />
        <ClientCard
          label="SABnzbd"
          online={sab?.online ?? false}
          speed={sab?.speed_mbps ?? 0}
          active={sab?.active_downloads ?? 0}
          queue={sab?.queue_size ?? 0}
          paused={sab?.paused}
        />
      </div>
    </div>
  )
}
