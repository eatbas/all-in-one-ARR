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
import { Badge } from "@/shared/components/ui/badge"
import { Button } from "@/shared/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card"
import { SettingsHelp } from "@/shared/components/settings-help"
import { Switch } from "@/shared/components/ui/switch"
import { formatTimestamp } from "@/shared/lib/format"
import {
  useFindarrStatus,
  useResetFindarrState,
  useRunFindarr,
  useUpdateFindarrSettings,
} from "@/shared/lib/queries"
import type { FindarrAppName } from "@/shared/lib/api"

const APP_LABELS: Record<FindarrAppName, string> = {
  sonarr: "Sonarr",
  radarr: "Radarr",
}

export function Status() {
  const { data: status, isLoading } = useFindarrStatus()
  const updateSettings = useUpdateFindarrSettings()
  const runFindarr = useRunFindarr()
  const resetState = useResetFindarrState()

  if (isLoading || !status) {
    return <p className="text-sm text-muted-foreground">Loading Findarr…</p>
  }

  const enabled = status.settings.enabled

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <div className="min-w-0">
            <p className="font-medium">System Status</p>
            <p className="text-sm text-muted-foreground">
              {status.last_run_at
                ? `Last run: ${formatTimestamp(status.last_run_at)}`
                : "Waiting for first run…"}
            </p>
            <p className="text-sm text-muted-foreground">
              {status.last_run_detail ?? "No run details yet"}
            </p>
          </div>
          <div className="flex items-center gap-3 sm:ml-8">
            <Switch
              aria-label="Enable Findarr"
              checked={enabled}
              disabled={updateSettings.isPending}
              onCheckedChange={(checked) =>
                updateSettings.mutate({ enabled: checked })
              }
            />
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-medium">
                {enabled ? "Enabled" : "Disabled"}
              </span>
              <SettingsHelp label="Enable Findarr">
                Allows the scheduler to run bounded missing and upgrade searches.
              </SettingsHelp>
            </div>
          </div>
          <Badge variant={status.running ? "destructive" : "default"} className="sm:ml-auto">
            {status.running ? "Running" : status.last_run_status ?? "Idle"}
          </Badge>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Hourly cap</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">{status.hourly.remaining}</p>
            <p className="text-sm text-muted-foreground">
              remaining of {status.hourly.limit}; {status.hourly.used} used
            </p>
          </CardContent>
        </Card>
        {(["sonarr", "radarr"] as const).map((app) => {
          const appStatus = status.apps[app]
          return (
            <Card key={app}>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle>{APP_LABELS[app]}</CardTitle>
                  <Badge variant={appStatus.compatible ? "default" : "outline"}>
                    {appStatus.compatible ? "Compatible" : "Unchecked"}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                <p className="text-sm text-muted-foreground">{appStatus.detail}</p>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <p className="text-muted-foreground">Missing</p>
                    <p className="text-xl font-semibold">
                      {appStatus.processed.missing}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Upgrades</p>
                    <p className="text-xl font-semibold">
                      {appStatus.processed.upgrade}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <div className="flex flex-wrap gap-3">
        <div className="flex items-center gap-1.5">
          <Button
            onClick={() => runFindarr.mutate(undefined)}
            disabled={runFindarr.isPending}
          >
            <PlayIcon className="size-4" />
            Run all
          </Button>
          <SettingsHelp label="Run all">
            Starts a manual Findarr run immediately, respecting configured
            limits.
          </SettingsHelp>
        </div>
        <div className="flex items-center gap-1.5">
          <Button
            variant="outline"
            onClick={() => runFindarr.mutate("sonarr")}
            disabled={runFindarr.isPending}
          >
            <PlayIcon className="size-4" />
            Run Sonarr
          </Button>
          <SettingsHelp label="Run Sonarr">
            Starts a manual Sonarr Findarr run immediately, respecting configured
            limits.
          </SettingsHelp>
        </div>
        <div className="flex items-center gap-1.5">
          <Button
            variant="outline"
            onClick={() => runFindarr.mutate("radarr")}
            disabled={runFindarr.isPending}
          >
            <PlayIcon className="size-4" />
            Run Radarr
          </Button>
          <SettingsHelp label="Run Radarr">
            Starts a manual Radarr Findarr run immediately, respecting configured
            limits.
          </SettingsHelp>
        </div>
        <div className="flex items-center gap-1.5">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" disabled={resetState.isPending}>
                <RotateCcwIcon className="size-4" />
                Reset state
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
                <AlertDialogAction onClick={() => resetState.mutate()}>
                  Reset state
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <SettingsHelp label="Reset Findarr state">
            Allows previously processed items to be considered again; it does not
            delete media.
          </SettingsHelp>
        </div>
      </div>
    </div>
  )
}
