import { Card, CardContent } from "@/shared/components/ui/card"
import { SettingsHelp } from "@/shared/components/settings-help"
import { Switch } from "@/shared/components/ui/switch"
import { formatTimestamp } from "@/shared/lib/format"
import { LiveFindsPanel } from "@/features/findarr/components/live-finds-panel"
import {
  useFindarrStatus,
  useResetFindarrState,
  useRunFindarr,
  useUpdateFindarrSettings,
} from "@/shared/lib/queries"

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
        <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="font-medium">System Status</p>
            <p className="text-sm text-muted-foreground">
              {status.last_run_at
                ? `Last run: ${formatTimestamp(status.last_run_at)}`
                : "Waiting for first run…"}
            </p>
          </div>
          <div className="flex items-center gap-3">
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
                Allows the scheduler to run bounded missing and upgrade
                searches.
              </SettingsHelp>
            </div>
          </div>
        </CardContent>
      </Card>

      <LiveFindsPanel
        status={status}
        onRunAll={() => runFindarr.mutate(undefined)}
        onRunApp={(app) => runFindarr.mutate(app)}
        isRunning={runFindarr.isPending}
        onReset={() => resetState.mutate()}
        isResetting={resetState.isPending}
      />
    </div>
  )
}
