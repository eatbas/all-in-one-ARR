import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { Input } from "@/shared/components/ui/input"
import { SettingsHelp } from "@/shared/components/settings-help"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select"
import { Switch } from "@/shared/components/ui/switch"
import {
  useFindarrSettings,
  useUpdateFindarrSettings,
} from "@/shared/lib/queries"
import type {
  FindarrAppName,
  FindarrAppSettings,
  FindarrSettingsUpdate,
} from "@/shared/lib/api"

const INTERVAL_OPTIONS = [15, 30, 45, 60] as const
const APP_LABELS: Record<FindarrAppName, string> = {
  sonarr: "Sonarr",
  radarr: "Radarr",
}

function NumberInput({
  id,
  label,
  value,
  helpText,
  onChange,
  inline = false,
}: {
  id: string
  label: string
  value: number
  helpText: string
  onChange: (value: number) => void
  inline?: boolean
}) {
  const labelGroup = (
    <div className="flex items-center gap-1.5">
      <label htmlFor={id} className="font-medium">
        {label}
      </label>
      <SettingsHelp label={label}>{helpText}</SettingsHelp>
    </div>
  )
  const input = (
    <Input
      id={id}
      type="number"
      min={label === "Queue limit" ? -1 : 0}
      max={100}
      value={value}
      onChange={(event) => onChange(Number(event.target.value))}
    />
  )
  if (inline) {
    return (
      <div className="flex items-center gap-3 text-sm">
        <div className="shrink-0">{labelGroup}</div>
        <div className="flex-1">{input}</div>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-1 text-sm">
      {labelGroup}
      {input}
    </div>
  )
}

export function Settings() {
  const { data: settings, isLoading } = useFindarrSettings()
  const updateSettings = useUpdateFindarrSettings()

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
                Allows the scheduler to run bounded missing and upgrade searches.
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
        <CardContent className="grid gap-5 lg:grid-cols-3">
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
              onValueChange={(value) => update({ interval_minutes: Number(value) })}
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
            inline
          />
          <NumberInput
            id="findarr-queue-limit"
            label="Queue limit"
            value={settings.queue_limit}
            helpText="Stops Findarr when the Arr queue is above this size; -1 disables this guard."
            onChange={(value) => update({ queue_limit: value })}
            inline
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
                    onCheckedChange={(checked) => updateApp(app, { enabled: checked })}
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
                  inline
                />
                <NumberInput
                  id={`${app}-upgrade-limit`}
                  label="Upgrades per cycle"
                  value={appSettings.upgrade_limit}
                  helpText="Maximum quality-upgrade searches for this app in one Findarr cycle."
                  onChange={(value) => updateApp(app, { upgrade_limit: value })}
                  inline
                />
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
