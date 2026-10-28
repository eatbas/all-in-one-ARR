import { PlayIcon } from "lucide-react"

import { ConnectionBadge } from "@/shared/components/connection-badge"
import { Button } from "@/shared/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { ClearStrikesDialog } from "@/features/cleanarr/components/clear-strikes-dialog"
import { sourceLabel } from "@/features/cleanarr/labels"
import type { CleanarrStatus } from "@/shared/lib/api"

// Display order of the connection rows (the backend lists SABnzbd first).
const CONNECTION_ORDER = ["sonarr", "radarr", "sabnzbd"]

interface ConnectionsCardProps {
  status: CleanarrStatus
  onRun: () => void
  isRunning: boolean
  onClearStrikes: () => void
  isClearing: boolean
}

/** Per-app connection results of the last run, with Run now and Clear strikes. */
export function ConnectionsCard({
  status,
  onRun,
  isRunning,
  onClearStrikes,
  isClearing,
}: ConnectionsCardProps) {
  const totalStrikes = status.strikes.sonarr + status.strikes.radarr
  const connections = [...status.connections].sort(
    (left, right) =>
      CONNECTION_ORDER.indexOf(left.app) - CONNECTION_ORDER.indexOf(right.app),
  )

  return (
    <Card>
      <CardHeader className="items-center">
        <CardTitle>Connections</CardTitle>
        <CardAction className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            onClick={onRun}
            disabled={!status.enabled || status.running || isRunning}
          >
            <PlayIcon className="size-4" />
            Run now
          </Button>
          <ClearStrikesDialog
            total={totalStrikes}
            onConfirm={onClearStrikes}
            disabled={totalStrikes === 0 || isClearing}
          />
        </CardAction>
      </CardHeader>
      <CardContent>
        {!status.enabled ? (
          <p className="text-sm text-muted-foreground">
            Cleanarr is disabled. Enable it to run the scheduled clean or to run
            it now.
          </p>
        ) : connections.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Connections are checked on each run. Run Cleanarr now to check them.
          </p>
        ) : (
          <div className="grid gap-3 md:grid-cols-3">
            {connections.map((connection) => (
              <div
                key={connection.app}
                className="flex items-start justify-between gap-3 rounded-lg border p-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium">
                    {sourceLabel(connection.app)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {connection.detail}
                  </p>
                </div>
                <ConnectionBadge
                  state={connection.ok ? "connected" : "offline"}
                  detail={connection.detail}
                />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
