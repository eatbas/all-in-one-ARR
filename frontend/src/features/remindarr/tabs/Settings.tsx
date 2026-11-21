import { useState } from "react"
import { RefreshCwIcon, SaveIcon, SettingsIcon } from "lucide-react"

import { SettingsHelp } from "@/shared/components/settings-help"
import { Button } from "@/shared/components/ui/button"
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
import { Switch } from "@/shared/components/ui/switch"
import { TagChecklist } from "@/features/remindarr/components/tag-checklist"
import { intervalLabel, REMINDARR_INTERVALS } from "@/features/remindarr/labels"
import type {
  RemindarrSettings,
  RemindarrSettingsUpdate,
} from "@/shared/lib/api"
import {
  useRemindarrSettings,
  useUpdateRemindarrSettings,
} from "@/shared/lib/queries"

type ToggleKey = "enabled" | "monitored_only"

const TOGGLE_FIELDS: Readonly<
  Record<ToggleKey, { label: string; help: string }>
> = {
  enabled: {
    label: "Run the scheduled refresh",
    help: "Checks Plex for unwatched episodes on the interval below. While off, nothing is fetched and the menu badge is hidden.",
  },
  monitored_only: {
    label: "Monitored series and episodes only",
    help: "Skip unmonitored series and episodes, so episodes you stopped tracking in Sonarr never appear as reminders.",
  },
}

interface Drafts {
  enabled: boolean
  monitored_only: boolean
  interval_minutes: number
  tag_ids: number[]
}

/** Whether two id selections hold the same values, ignoring order. */
function sameSelection(left: number[], right: number[]): boolean {
  const sortedLeft = [...left].sort((a, b) => a - b)
  const sortedRight = [...right].sort((a, b) => a - b)
  return (
    sortedLeft.length === sortedRight.length &&
    sortedLeft.every((tagId, index) => tagId === sortedRight[index])
  )
}

/** Return only the fields that differ from the saved settings. */
function buildUpdate(
  drafts: Drafts,
  settings: RemindarrSettings,
): RemindarrSettingsUpdate {
  const update: RemindarrSettingsUpdate = {}
  if (drafts.enabled !== settings.enabled) update.enabled = drafts.enabled
  if (drafts.monitored_only !== settings.monitored_only) {
    update.monitored_only = drafts.monitored_only
  }
  if (drafts.interval_minutes !== settings.interval_minutes) {
    update.interval_minutes = drafts.interval_minutes
  }
  if (!sameSelection(drafts.tag_ids, settings.tag_ids)) {
    update.tag_ids = drafts.tag_ids
  }
  return update
}

/** The offered intervals, plus a saved value outside them so it stays shown. */
function intervalOptions(saved: number): number[] {
  return REMINDARR_INTERVALS.includes(saved)
    ? [...REMINDARR_INTERVALS]
    : [...REMINDARR_INTERVALS, saved].sort((a, b) => a - b)
}

interface ToggleRowProps {
  field: ToggleKey
  checked: boolean
  onChange: (checked: boolean) => void
  disabled: boolean
}

function ToggleRow({ field, checked, onChange, disabled }: ToggleRowProps) {
  const { label, help } = TOGGLE_FIELDS[field]
  const id = `remindarr-${field}`
  return (
    <div className="flex items-start justify-between gap-4 rounded-md border p-3">
      <div className="grid gap-1">
        <label htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
        <p className="text-xs text-muted-foreground">{help}</p>
      </div>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
        aria-label={label}
      />
    </div>
  )
}

interface SettingsFormProps {
  settings: RemindarrSettings
  onSave: (update: RemindarrSettingsUpdate) => void
  isPending: boolean
}

/** Form state is scoped to one known settings snapshot via the parent key. */
function SettingsForm({ settings, onSave, isPending }: SettingsFormProps) {
  const [drafts, setDrafts] = useState<Drafts>({
    enabled: settings.enabled,
    monitored_only: settings.monitored_only,
    interval_minutes: settings.interval_minutes,
    tag_ids: settings.tag_ids,
  })
  const update = buildUpdate(drafts, settings)
  const canSave = Object.keys(update).length > 0

  function setDraft<K extends keyof Drafts>(key: K, value: Drafts[K]) {
    setDrafts((current) => ({ ...current, [key]: value }))
  }

  return (
    <Card className="max-w-[860px]">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <SettingsIcon className="size-4 text-muted-foreground" />
          Remindarr settings
        </CardTitle>
        <CardDescription>
          Which Sonarr series to track and how often to check their watch state
          in Plex.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        <ToggleRow
          field="enabled"
          checked={drafts.enabled}
          onChange={(checked) => setDraft("enabled", checked)}
          disabled={isPending}
        />
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-1.5">
            <label htmlFor="remindarr-interval" className="text-sm font-medium">
              Refresh interval
            </label>
            <SettingsHelp label="Refresh interval">
              How often Remindarr reads Sonarr and Plex. Each refresh lists
              every tracked show, so prefer longer intervals on large libraries.
            </SettingsHelp>
          </div>
          <Select
            value={String(drafts.interval_minutes)}
            onValueChange={(value) =>
              setDraft("interval_minutes", Number(value))
            }
            disabled={isPending}
          >
            <SelectTrigger id="remindarr-interval" className="w-full sm:w-40">
              <SelectValue placeholder="Select interval" />
            </SelectTrigger>
            <SelectContent>
              {intervalOptions(settings.interval_minutes).map((minutes) => (
                <SelectItem key={minutes} value={String(minutes)}>
                  {intervalLabel(minutes)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <TagChecklist
          selected={drafts.tag_ids}
          onChange={(tagIds) => setDraft("tag_ids", tagIds)}
          disabled={isPending}
        />
        <ToggleRow
          field="monitored_only"
          checked={drafts.monitored_only}
          onChange={(checked) => setDraft("monitored_only", checked)}
          disabled={isPending}
        />
        <div className="flex justify-end">
          <Button
            type="button"
            onClick={() => onSave(update)}
            disabled={!canSave || isPending}
          >
            <SaveIcon className="size-4" />
            Save
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

/** Remindarr Settings tab. */
export function Settings() {
  const {
    data: settings,
    isLoading,
    isError,
    error,
    isFetching,
    refetch,
  } = useRemindarrSettings()
  const updateSettings = useUpdateRemindarrSettings()

  // A failed background refetch keeps the cached settings and the form (and
  // any unsaved drafts); only a load that never produced settings is an error.
  if (isError && !settings) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-sm text-destructive">
          Could not load Remindarr settings: {error.message}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void refetch()}
          disabled={isFetching}
        >
          <RefreshCwIcon
            className={isFetching ? "size-4 animate-spin" : "size-4"}
          />
          Try again
        </Button>
      </div>
    )
  }
  if (isLoading || !settings) {
    return (
      <p className="text-sm text-muted-foreground">
        Loading Remindarr settings…
      </p>
    )
  }

  return (
    <SettingsForm
      key={JSON.stringify(settings)}
      settings={settings}
      onSave={(update) => updateSettings.mutate(update)}
      isPending={updateSettings.isPending}
    />
  )
}
