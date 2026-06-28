import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select"
import { SettingsHelp } from "@/shared/components/settings-help"
import { Switch } from "@/shared/components/ui/switch"
import { TraktListSelector } from "@/features/list-syncarr/components/trakt-list-selector"
import {
  useGeneralSettings,
  useUpdateAutoRemoveWhenAvailable,
  useUpdateSyncInterval,
} from "@/shared/lib/queries"

const SYNC_INTERVAL_OPTIONS = [15, 30, 45, 60] as const

/**
 * List-Syncarr Settings tab: choose which Trakt lists to keep in sync and
 * configure sync behaviour.
 */
export function ListSettings() {
  const { data: general } = useGeneralSettings()
  const updateSyncInterval = useUpdateSyncInterval()
  const updateAutoRemove = useUpdateAutoRemoveWhenAvailable()

  const autoRemoveWhenAvailable = general?.auto_remove_when_available ?? false
  const syncInterval = general?.sync_interval_minutes ?? 15

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Choose which Trakt lists the engine keeps in sync, and how it polls and
          removes them.
        </p>
      </div>

      <TraktListSelector />

      <Card>
        <CardHeader>
          <CardTitle>Sync behaviour</CardTitle>
          <CardDescription>
            Control how often lists are polled and whether imported items are
            removed automatically.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-1.5">
                <p className="text-sm font-medium">
                  Remove from Trakt when available
                </p>
                <SettingsHelp label="Remove from Trakt when available">
                  Removes the list entry when Seer reports the item available;
                  media files are untouched.
                </SettingsHelp>
              </div>
              <p className="text-sm text-muted-foreground">
                When on, an item is removed from its Trakt list as soon as
                Seer reports it available — the list entry only; the media
                files in Radarr/Sonarr are untouched. When off, removal is manual —
                use the controls in the Lists tab.
              </p>
            </div>
            <Switch
              aria-label="Toggle remove from Trakt when available"
              checked={autoRemoveWhenAvailable}
              disabled={updateAutoRemove.isPending}
              onCheckedChange={(checked) => updateAutoRemove.mutate(checked)}
            />
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-1.5">
              <label htmlFor="sync-interval" className="text-sm font-medium">
                Sync interval
              </label>
              <SettingsHelp label="Sync interval">
                How often List-Syncarr polls Trakt and requests missing items in
                Seer.
              </SettingsHelp>
            </div>
            <p className="text-sm text-muted-foreground">
              How often the engine polls Trakt and requests in Seer.
            </p>
            <Select
              value={String(syncInterval)}
              onValueChange={(value) => updateSyncInterval.mutate(Number(value))}
              disabled={updateSyncInterval.isPending}
            >
              <SelectTrigger id="sync-interval" className="w-40">
                <SelectValue placeholder="Select interval" />
              </SelectTrigger>
              <SelectContent>
                {SYNC_INTERVAL_OPTIONS.map((minutes) => (
                  <SelectItem key={minutes} value={String(minutes)}>
                    {minutes} minutes
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
