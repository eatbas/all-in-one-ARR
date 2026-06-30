import { PlayIcon } from "lucide-react"

import { Button } from "@/shared/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card"
import { FindarrAppCard } from "@/features/findarr/components/app-card"
import { FindarrResetDialog } from "@/features/findarr/components/reset-dialog"
import { formatCountdown } from "@/shared/lib/format"
import type { FindarrAppName, FindarrStatus } from "@/shared/lib/api"

const APPS: readonly FindarrAppName[] = ["sonarr", "radarr"]

interface LiveFindsPanelProps {
  status: FindarrStatus
  onRunAll: () => void
  onRunApp: (app: FindarrAppName) => void
  isRunning: boolean
  onReset: () => void
  isResetting: boolean
}

/**
 * "Live Finds Executed" panel: the two per-app display cards, with the hourly
 * cap and the global Run all / Reset controls in the header (top-right),
 * mirroring the reference layout.
 */
export function LiveFindsPanel({
  status,
  onRunAll,
  onRunApp,
  isRunning,
  onReset,
  isResetting,
}: LiveFindsPanelProps) {
  const { hourly, state } = status

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle>Live Finds Executed</CardTitle>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-muted-foreground">
            {`Next sweep ${formatCountdown(state.reset_at)}`}
          </span>
          <span className="text-sm text-muted-foreground">
            {`${hourly.limit}/${hourly.remaining} Left`}
          </span>
          <Button size="sm" onClick={onRunAll} disabled={isRunning}>
            <PlayIcon className="size-4" />
            Run all
          </Button>
          <FindarrResetDialog
            triggerLabel="Reset"
            description="This allows Findarr to consider previously processed Sonarr and Radarr items again. It does not delete media or change Arr libraries."
            onConfirm={onReset}
            disabled={isResetting}
          />
        </div>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-2">
        {APPS.map((app) => (
          <FindarrAppCard
            key={app}
            app={app}
            status={status.apps[app]}
            hourly={hourly}
            enabled={status.settings.enabled && status.settings.apps[app].enabled}
            onRun={() => onRunApp(app)}
            isRunning={isRunning}
          />
        ))}
      </CardContent>
    </Card>
  )
}
