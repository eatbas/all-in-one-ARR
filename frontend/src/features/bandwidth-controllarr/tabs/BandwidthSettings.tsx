import { useState } from "react"
import { ExternalLinkIcon } from "lucide-react"

import { Button } from "@/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { Input } from "@/shared/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select"
import { Switch } from "@/shared/components/ui/switch"
import {
  useBandwidthStatus,
  useUpdateBandwidthSettings,
} from "@/shared/lib/queries"
import { SettingsHelp } from "@/shared/components/settings-help"

const INTERVAL_OPTIONS = [10, 15, 30, 60] as const

/** Bounds mirrored from the backend's SABnzbd limiter validation (MB/s). */
const SAB_LIMIT_MBPS_MIN = 0.1
const SAB_LIMIT_MBPS_MAX = 1024

/**
 * Bandwidth-Controllarr Settings tab: choose the control-loop check interval,
 * cap SABnzbd's download speed, and expose a link to the Prometheus metrics.
 */
export function BandwidthSettings() {
  const { data: status } = useBandwidthStatus()
  const updateSettings = useUpdateBandwidthSettings()

  const interval = status?.check_interval_seconds ?? 15
  const sabLimitEnabled = status?.sab_limit_enabled ?? false
  const sabLimitMbps = status?.sab_limit_mbps ?? 5

  // The status query re-polls every few seconds, so a controlled input bound
  // straight to the server value would be overwritten mid-edit. A null draft
  // means "not editing — show the server value"; the draft is committed on
  // blur or Enter, never per keystroke (each PUT drives a live SABnzbd call).
  const [limitDraft, setLimitDraft] = useState<string | null>(null)

  function commitLimit() {
    if (limitDraft === null) return
    setLimitDraft(null)
    const parsed = Number(limitDraft)
    if (!Number.isFinite(parsed) || parsed <= 0) return
    const bounded = Math.min(
      Math.max(parsed, SAB_LIMIT_MBPS_MIN),
      SAB_LIMIT_MBPS_MAX,
    )
    if (bounded === sabLimitMbps) return
    updateSettings.mutate({ sab_limit_mbps: bounded })
  }

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
              <div className="flex items-center gap-1.5">
                <label htmlFor="check-interval" className="text-sm font-medium">
                  Check interval
                </label>
                <SettingsHelp label="Check interval">
                  How often the bandwidth loop checks qBittorrent and SABnzbd.
                </SettingsHelp>
              </div>
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

          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-1.5">
                <label htmlFor="sab-limit-mbps" className="text-sm font-medium">
                  Download limit (MB/s)
                </label>
                <SettingsHelp label="Download limit (MB/s)">
                  Caps SABnzbd&apos;s download speed at the configured MB/s. The
                  cap is re-applied if SABnzbd loses it, for example after a
                  restart.
                </SettingsHelp>
              </div>
              <p className="text-sm text-muted-foreground">
                The SABnzbd download limiter holds downloads to a fixed speed.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Switch
                aria-label="SABnzbd download limiter"
                checked={sabLimitEnabled}
                disabled={updateSettings.isPending}
                onCheckedChange={(checked) =>
                  updateSettings.mutate({ sab_limit_enabled: checked })
                }
              />
              <Input
                id="sab-limit-mbps"
                type="number"
                inputMode="decimal"
                min={SAB_LIMIT_MBPS_MIN}
                max={SAB_LIMIT_MBPS_MAX}
                step={0.1}
                className="w-full sm:w-28"
                value={limitDraft ?? String(sabLimitMbps)}
                disabled={!sabLimitEnabled || updateSettings.isPending}
                onChange={(event) => setLimitDraft(event.target.value)}
                onBlur={commitLimit}
                onKeyDown={(event) => {
                  if (event.key === "Enter") commitLimit()
                }}
              />
            </div>
          </div>

          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium">Prometheus metrics</p>
              <p className="text-sm text-muted-foreground">
                Scrape-compatible <code>bw_*</code> gauges exposed at{" "}
                <code>/metrics</code>.
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              <Button asChild variant="outline" size="sm">
                <a href="/metrics" target="_blank" rel="noreferrer">
                  <ExternalLinkIcon className="size-4" />
                  Open /metrics
                </a>
              </Button>
              <SettingsHelp label="Open metrics">
                Opens the Prometheus scrape endpoint for bandwidth control
                gauges.
              </SettingsHelp>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
