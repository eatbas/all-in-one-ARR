import { FlaskConicalIcon } from "lucide-react"

import { ConnectionsCard } from "@/features/cleanarr/components/connections-card"
import { HealthCard } from "@/features/cleanarr/components/health-card"
import { SettingsHelp } from "@/shared/components/settings-help"
import { StatBlock } from "@/shared/components/stat-block"
import { Card, CardContent } from "@/shared/components/ui/card"
import { Switch } from "@/shared/components/ui/switch"
import { formatTimestamp } from "@/shared/lib/format"
import {
  useCleanarrStatus,
  useClearCleanarrStrikes,
  useRunCleanarr,
  useUpdateCleanarrSettings,
} from "@/shared/lib/queries"

/** Amber banner shown while dry run is on: nothing is changed. */
function DryRunBanner() {
  return (
    <div
      role="status"
      className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-50 p-4 dark:bg-amber-950/30"
    >
      <span className="mt-0.5 text-amber-600 dark:text-amber-400">
        <FlaskConicalIcon className="size-4" aria-hidden="true" />
      </span>
      <div>
        <p className="text-sm font-semibold">
          Dry run is on. No changes are made.
        </p>
        <p className="text-sm text-muted-foreground">
          Cleanarr counts strikes and records in History what it would remove,
          delete or quarantine. Turn dry run off in Settings once the results
          look right.
        </p>
      </div>
    </div>
  )
}

/** Cleanarr Status tab: switch, last run, connections, strikes and health. */
export function Status() {
  const { data: status, isLoading, isError, error } = useCleanarrStatus()
  const updateSettings = useUpdateCleanarrSettings()
  const runCleanarr = useRunCleanarr()
  const clearStrikes = useClearCleanarrStrikes()

  if (isError) {
    return (
      <p className="text-sm text-destructive">
        Could not load Cleanarr: {error.message}
      </p>
    )
  }
  if (isLoading || !status) {
    return <p className="text-sm text-muted-foreground">Loading Cleanarr…</p>
  }

  const lastRun = status.last_run
  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="font-medium">System Status</p>
            <p className="text-sm text-muted-foreground">
              {lastRun
                ? `Last run: ${formatTimestamp(lastRun.at)} · ${lastRun.detail}`
                : "Waiting for first run…"}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Switch
              aria-label="Enable Cleanarr"
              checked={status.enabled}
              disabled={updateSettings.isPending}
              onCheckedChange={(checked) =>
                updateSettings.mutate({ enabled: checked })
              }
            />
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-medium">
                {status.enabled ? "Enabled" : "Disabled"}
              </span>
              <SettingsHelp label="Enable Cleanarr">
                Allows the scheduler to strike and clean stuck Sonarr/Radarr
                queue items every {status.settings.interval_minutes} minutes.
              </SettingsHelp>
            </div>
          </div>
        </CardContent>
      </Card>

      {status.dry_run ? <DryRunBanner /> : null}

      <ConnectionsCard
        status={status}
        onRun={() => runCleanarr.mutate()}
        isRunning={runCleanarr.isPending}
        onClearStrikes={() => clearStrikes.mutate()}
        isClearing={clearStrikes.isPending}
      />

      <section
        aria-label="Strike counts"
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
      >
        <StatBlock label="Sonarr strikes" value={status.strikes.sonarr} />
        <StatBlock label="Radarr strikes" value={status.strikes.radarr} />
        <StatBlock
          label="Failed imports"
          value={status.strikes.failed_import}
        />
        <StatBlock
          label="Failed downloads"
          value={status.strikes.failed_download}
        />
      </section>

      <HealthCard health={status.health} hasRun={lastRun !== null} />
    </div>
  )
}
