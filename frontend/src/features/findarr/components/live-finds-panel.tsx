import { PlayIcon, RotateCcwIcon } from "lucide-react"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/components/ui/alert-dialog"
import { Button } from "@/shared/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card"
import { FindarrAppCard } from "@/features/findarr/components/app-card"
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
  const { hourly } = status

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle>Live Finds Executed</CardTitle>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-muted-foreground">
            {`${hourly.limit}/${hourly.remaining} Left`}
          </span>
          <Button size="sm" onClick={onRunAll} disabled={isRunning}>
            <PlayIcon className="size-4" />
            Run all
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button size="sm" variant="destructive" disabled={isResetting}>
                <RotateCcwIcon className="size-4" />
                Reset
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Reset Findarr processed state?</AlertDialogTitle>
                <AlertDialogDescription>
                  This allows Findarr to consider previously processed Sonarr and
                  Radarr items again. It does not delete media or change Arr
                  libraries.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={onReset}>Reset</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-2">
        {APPS.map((app) => (
          <FindarrAppCard
            key={app}
            app={app}
            processed={status.apps[app].processed}
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
