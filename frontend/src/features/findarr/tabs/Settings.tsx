import { Badge } from "@/shared/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card"
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
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (value: number) => void
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium">{label}</span>
      <Input
        type="number"
        min={label === "Queue limit" ? -1 : 0}
        max={100}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
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
        </CardHeader>
        <CardContent className="grid gap-5 lg:grid-cols-4">
          <div className="flex items-center gap-3">
            <Switch
              aria-label="Enable Findarr"
              checked={settings.enabled}
              disabled={updateSettings.isPending}
              onCheckedChange={(checked) => update({ enabled: checked })}
            />
            <span className="text-sm font-medium">
              {settings.enabled ? "Enabled" : "Disabled"}
            </span>
          </div>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">Interval</span>
            <Select
              value={String(settings.interval_minutes)}
              onValueChange={(value) => update({ interval_minutes: Number(value) })}
            >
              <SelectTrigger>
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
          </label>
          <NumberInput
            label="Hourly cap"
            value={settings.hourly_cap}
            onChange={(value) => update({ hourly_cap: value })}
          />
          <NumberInput
            label="Queue limit"
            value={settings.queue_limit}
            onChange={(value) => update({ queue_limit: value })}
          />
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        {(["sonarr", "radarr"] as const).map((app) => {
          const appSettings = settings.apps[app]
          return (
            <Card key={app}>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle>{APP_LABELS[app]}</CardTitle>
                  <Badge variant={appSettings.enabled ? "default" : "outline"}>
                    {appSettings.enabled ? "Enabled" : "Disabled"}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="grid gap-5 sm:grid-cols-2">
                <div className="flex items-center gap-3">
                  <Switch
                    aria-label={`Enable ${APP_LABELS[app]}`}
                    checked={appSettings.enabled}
                    onCheckedChange={(checked) => updateApp(app, { enabled: checked })}
                  />
                  <span className="text-sm font-medium">Process app</span>
                </div>
                <div className="flex items-center gap-3">
                  <Switch
                    aria-label={`${APP_LABELS[app]} monitored only`}
                    checked={appSettings.monitored_only}
                    onCheckedChange={(checked) =>
                      updateApp(app, { monitored_only: checked })
                    }
                  />
                  <span className="text-sm font-medium">Monitored only</span>
                </div>
                <div className="flex items-center gap-3">
                  <Switch
                    aria-label={`${APP_LABELS[app]} skip future`}
                    checked={appSettings.skip_future}
                    onCheckedChange={(checked) =>
                      updateApp(app, { skip_future: checked })
                    }
                  />
                  <span className="text-sm font-medium">Skip future</span>
                </div>
                <NumberInput
                  label="Missing per cycle"
                  value={appSettings.missing_limit}
                  onChange={(value) => updateApp(app, { missing_limit: value })}
                />
                <NumberInput
                  label="Upgrades per cycle"
                  value={appSettings.upgrade_limit}
                  onChange={(value) => updateApp(app, { upgrade_limit: value })}
                />
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
