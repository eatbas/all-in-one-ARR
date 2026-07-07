import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { Input } from "@/shared/components/ui/input"
import { SettingsHelp } from "@/shared/components/settings-help"
import { FindarrResetDialog } from "@/features/findarr/components/reset-dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select"
import { Switch } from "@/shared/components/ui/switch"
import { formatTimestamp } from "@/shared/lib/format"
import {
  useFindarrSettings,
  useFindarrStatus,
  useResetFindarrState,
  useUpdateFindarrSettings,
} from "@/shared/lib/queries"
import type {
  FindarrAppName,
  FindarrAppSettings,
  FindarrSearchMode,
  FindarrSettingsUpdate,
} from "@/shared/lib/api"

const INTERVAL_OPTIONS = [15, 30, 45, 60] as const
const APP_LABELS: Record<FindarrAppName, string> = {
  sonarr: "Sonarr",
  radarr: "Radarr",
}
const SEARCH_MODE_OPTIONS: { value: FindarrSearchMode; label: string }[] = [
  { value: "episodes", label: "Episodes" },
  { value: "seasons", label: "Seasons" },
  { value: "shows", label: "Shows" },
]

function NumberInput({
  id,
  label,
  value,
  helpText,
  onChange,
  min = 0,
  max = 100,
}: {
  id: string
  label: string
  value: number
  helpText: string
  onChange: (value: number) => void
  min?: number
  max?: number
}) {
  return (
    <div className="flex items-center gap-3 text-sm">
      <div className="shrink-0">
        <div className="flex items-center gap-1.5">
          <label htmlFor={id} className="font-medium">
            {label}
          </label>
          <SettingsHelp label={label}>{helpText}</SettingsHelp>
        </div>
      </div>
      <div className="flex-1">
        <Input
          id={id}
          type="number"
          min={min}
          max={max}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      </div>
    </div>
  )
}

function ModeSelect({
  id,
  label,
  value,
  helpText,
  onChange,
}: {
  id: string
  label: string
  value: FindarrSearchMode
  helpText: string
  onChange: (value: FindarrSearchMode) => void
}) {
  return (
    <div className="flex items-center gap-3 text-sm">
      <div className="flex shrink-0 items-center gap-1.5">
        <label htmlFor={id} className="font-medium">
          {label}
        </label>
        <SettingsHelp label={label}>{helpText}</SettingsHelp>
      </div>
      <Select
        value={value}
        onValueChange={(next) => onChange(next as FindarrSearchMode)}
      >
        <SelectTrigger id={id} className="flex-1">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {SEARCH_MODE_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

export function Settings() {
  const { data: settings, isLoading } = useFindarrSettings()
  const { data: status } = useFindarrStatus()
  const updateSettings = useUpdateFindarrSettings()
  const resetState = useResetFindarrState()

  if (isLoading || !settings) {
    return <p className="text-sm text-muted-foreground">Loading settings…</p>
  }

  function update(body: FindarrSettingsUpdate) {
    updateSettings.mutate(body)
  }

  function updateApp(app: FindarrAppName, body: Partial<FindarrAppSettings>) {
    update({ apps: { [app]: body } })
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Findarr scheduler</CardTitle>
          <CardAction className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-medium">
                {settings.enabled ? "Enabled" : "Disabled"}
              </span>
              <SettingsHelp label="Enable Findarr">
                Allows the scheduler to run bounded missing and upgrade
                searches.
              </SettingsHelp>
            </div>
            <Switch
              aria-label="Enable Findarr"
              checked={settings.enabled}
              disabled={updateSettings.isPending}
              onCheckedChange={(checked) => update({ enabled: checked })}
            />
          </CardAction>
        </CardHeader>
        <CardContent className="grid gap-5 lg:grid-cols-2">
          <div className="flex items-center gap-3 text-sm">
            <div className="flex shrink-0 items-center gap-1.5">
              <label htmlFor="findarr-interval" className="font-medium">
                Interval
              </label>
              <SettingsHelp label="Findarr interval">
                How often Findarr wakes up to run automatic searches.
              </SettingsHelp>
            </div>
            <Select
              value={String(settings.interval_minutes)}
              onValueChange={(value) =>
                update({ interval_minutes: Number(value) })
              }
            >
              <SelectTrigger id="findarr-interval" className="flex-1">
                <SelectValue placeholder="Interval" />
              </SelectTrigger>
              <SelectContent>
                {INTERVAL_OPTIONS.map((minutes) => (
                  <SelectItem key={minutes} value={String(minutes)}>
                    {minutes} minutes
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <NumberInput
            id="findarr-hourly-cap"
            label="Hourly cap"
            value={settings.hourly_cap}
            helpText="Maximum number of Findarr search commands allowed per hour."
            onChange={(value) => update({ hourly_cap: value })}
          />
          <NumberInput
            id="findarr-queue-limit"
            label="Queue limit"
            value={settings.queue_limit}
            min={-1}
            helpText="Stops Findarr when the Arr queue is above this size; -1 disables this guard."
            onChange={(value) => update({ queue_limit: value })}
          />
          <NumberInput
            id="findarr-sleep"
            label="Sleep duration"
            value={settings.command_sleep_seconds}
            min={0}
            max={60}
            helpText="Seconds to wait between successive Arr search commands, to throttle the API (0 disables)."
            onChange={(value) => update({ command_sleep_seconds: value })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Stateful management</CardTitle>
          <CardAction>
            <FindarrResetDialog
              triggerLabel="Emergency reset"
              description="This clears all processed media ids so Findarr re-considers every Sonarr and Radarr item and restarts the reset window. It never deletes media or changes Arr libraries."
              onConfirm={() => resetState.mutate()}
              disabled={resetState.isPending}
            />
          </CardAction>
        </CardHeader>
        <CardContent className="grid gap-5 lg:grid-cols-3">
          <div className="text-sm">
            <p className="font-medium">Initial state created</p>
            <p className="text-muted-foreground">
              {status?.state.created_at
                ? formatTimestamp(status.state.created_at)
                : "Not created yet"}
            </p>
          </div>
          <div className="text-sm">
            <p className="font-medium">State reset date</p>
            <p className="text-muted-foreground">
              {status?.state.reset_at
                ? formatTimestamp(status.state.reset_at)
                : "—"}
            </p>
          </div>
          <NumberInput
            id="findarr-state-reset-hours"
            label="State reset (hours)"
            value={settings.state_reset_hours}
            min={1}
            max={8760}
            helpText="Hours before Findarr clears processed media ids so items can be searched again."
            onChange={(value) => update({ state_reset_hours: value })}
          />
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        {(["sonarr", "radarr"] as const).map((app) => {
          const appSettings = settings.apps[app]
          return (
            <Card key={app}>
              <CardHeader>
                <CardTitle>{APP_LABELS[app]}</CardTitle>
                <CardAction className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-medium">Process app</span>
                    <SettingsHelp label={`${APP_LABELS[app]} process app`}>
                      Includes this Arr app in Findarr processing.
                    </SettingsHelp>
                  </div>
                  <Switch
                    aria-label={`Enable ${APP_LABELS[app]}`}
                    checked={appSettings.enabled}
                    onCheckedChange={(checked) =>
                      updateApp(app, { enabled: checked })
                    }
                  />
                </CardAction>
              </CardHeader>
              <CardContent className="grid gap-5 sm:grid-cols-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-medium">Monitored only</span>
                    <SettingsHelp label={`${APP_LABELS[app]} monitored only`}>
                      Searches only items marked monitored in the Arr app.
                    </SettingsHelp>
                  </div>
                  <Switch
                    aria-label={`${APP_LABELS[app]} monitored only`}
                    checked={appSettings.monitored_only}
                    onCheckedChange={(checked) =>
                      updateApp(app, { monitored_only: checked })
                    }
                  />
                </div>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-medium">Skip future</span>
                    <SettingsHelp label={`${APP_LABELS[app]} skip future`}>
                      Skips items whose release or air date is in the future.
                    </SettingsHelp>
                  </div>
                  <Switch
                    aria-label={`${APP_LABELS[app]} skip future`}
                    checked={appSettings.skip_future}
                    onCheckedChange={(checked) =>
                      updateApp(app, { skip_future: checked })
                    }
                  />
                </div>
                <NumberInput
                  id={`${app}-missing-limit`}
                  label="Missing per cycle"
                  value={appSettings.missing_limit}
                  helpText="Maximum missing-item searches for this app in one Findarr cycle."
                  onChange={(value) => updateApp(app, { missing_limit: value })}
                />
                <NumberInput
                  id={`${app}-upgrade-limit`}
                  label="Upgrades per cycle"
                  value={appSettings.upgrade_limit}
                  helpText="Maximum quality-upgrade searches for this app in one Findarr cycle."
                  onChange={(value) => updateApp(app, { upgrade_limit: value })}
                />
                {app === "sonarr" && (
                  <>
                    <ModeSelect
                      id="sonarr-missing-mode"
                      label="Missing search mode"
                      value={appSettings.missing_mode}
                      helpText="How to search missing Sonarr content (Seasons recommended for torrent users)."
                      onChange={(mode) =>
                        updateApp(app, { missing_mode: mode })
                      }
                    />
                    <ModeSelect
                      id="sonarr-upgrade-mode"
                      label="Upgrade mode"
                      value={appSettings.upgrade_mode}
                      helpText="How to search Sonarr upgrades (Seasons/Shows upgrade whole seasons or series at once)."
                      onChange={(mode) =>
                        updateApp(app, { upgrade_mode: mode })
                      }
                    />
                  </>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
