import { ExternalLinkIcon } from "lucide-react"

import { Button } from "@/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select"
import {
  useBandwidthStatus,
  useUpdateBandwidthSettings,
} from "@/shared/lib/queries"

const INTERVAL_OPTIONS = [10, 15, 30, 60] as const

/**
 * Bandwidth-Controllarr Settings tab: choose the control-loop check interval
 * and expose a link to the Prometheus metrics.
 */
export function BandwidthSettings() {
  const { data: status } = useBandwidthStatus()
  const updateSettings = useUpdateBandwidthSettings()

  const interval = status?.check_interval_seconds ?? 15

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Control when SABnzbd pauses and how often the loop checks the clients.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Bandwidth control</CardTitle>
          <CardDescription>
            When enabled, SABnzbd is paused while qBittorrent has active
            torrents and resumed when the torrents go idle.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <label htmlFor="check-interval" className="text-sm font-medium">
                Check interval
              </label>
              <p className="text-sm text-muted-foreground">
                How often the engine polls qBittorrent and SABnzbd.
              </p>
            </div>
            <Select
              value={String(interval)}
              onValueChange={(value) =>
                updateSettings.mutate({
                  check_interval_seconds: Number(value),
                })
              }
              disabled={updateSettings.isPending}
            >
              <SelectTrigger id="check-interval" className="w-full sm:w-40">
                <SelectValue placeholder="Select interval" />
              </SelectTrigger>
              <SelectContent>
                {INTERVAL_OPTIONS.map((seconds) => (
                  <SelectItem key={seconds} value={String(seconds)}>
                    {seconds} seconds
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium">Prometheus metrics</p>
              <p className="text-sm text-muted-foreground">
                Scrape-compatible <code>bw_*</code> gauges exposed at{" "}
                <code>/metrics</code>.
              </p>
            </div>
            <Button asChild variant="outline" size="sm">
              <a href="/metrics" target="_blank" rel="noreferrer">
                <ExternalLinkIcon className="size-4" />
                Open /metrics
              </a>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
