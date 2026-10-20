import { useState } from "react"
import { SaveIcon, SettingsIcon } from "lucide-react"

import { Button } from "@/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { Input } from "@/shared/components/ui/input"
import { Switch } from "@/shared/components/ui/switch"
import { LanguageChecklist } from "@/features/languagarr/components/language-checklist"
import { ProfileChecklist } from "@/features/languagarr/components/profile-checklist"
import {
  normaliseServiceUrl,
  type LanguagarrSettings,
  type LanguagarrSettingsUpdate,
} from "@/shared/lib/api"
import {
  useLanguagarrSettings,
  useUpdateLanguagarrSettings,
} from "@/shared/lib/queries"

type NumericKey = "interval_minutes" | "searches_per_run" | "retry_after_hours"
type ToggleKey = "enabled" | "auto_queue" | "monitored_only"

// Bounds mirror the backend's LANGUAGARR_* constants in
// backend/core/settings_normalisers.py, which the API also enforces (422).
const NUMERIC_FIELDS: ReadonlyArray<{
  key: NumericKey
  label: string
  help: string
  min: number
  max: number
}> = [
  {
    key: "interval_minutes",
    label: "Worker interval (minutes)",
    help: "How often the scheduled worker sends a batch of searches (15–1440).",
    min: 15,
    max: 1440,
  },
  {
    key: "searches_per_run",
    label: "Searches per run",
    help: "Episode searches sent per batch; keep low to respect indexer limits (1–100).",
    min: 1,
    max: 100,
  },
  {
    key: "retry_after_hours",
    label: "Retry after (hours)",
    help: "A searched file is not queued again until this long has passed (24–2160).",
    min: 24,
    max: 2160,
  },
]

const TOGGLE_FIELDS: ReadonlyArray<{
  key: ToggleKey
  label: string
  help: string
}> = [
  {
    key: "enabled",
    label: "Run the scheduled search worker",
    help: "Sends queued replacement searches to Sonarr on the interval below.",
  },
  {
    key: "auto_queue",
    label: "Scan and queue automatically",
    help: "Each worker run rescans and queues every file that a search can fix. Files needing a delete are never actioned automatically.",
  },
  {
    key: "monitored_only",
    label: "Monitored series and episodes only",
    help: "Skip unmonitored series and never search unmonitored episodes. Sonarr runs these searches as manual ones, which would otherwise replace files you froze.",
  },
]

interface Drafts {
  enabled: boolean
  auto_queue: boolean
  monitored_only: boolean
  interval_minutes: string
  searches_per_run: string
  retry_after_hours: string
  profiles: string[]
  languages: string[]
  sonarr_link_url: string
}

/** Normalised link URL (`""` clears it), or `null` for an unsupported scheme. */
function parseLinkUrl(value: string): string | null {
  try {
    return normaliseServiceUrl(value)
  } catch {
    return null
  }
}

/** Whether two selections hold the same values, ignoring order. */
function sameSelection(left: string[], right: string[]): boolean {
  const sortedLeft = [...left].sort()
  const sortedRight = [...right].sort()
  return (
    sortedLeft.length === sortedRight.length &&
    sortedLeft.every((name, index) => name === sortedRight[index])
  )
}

/** Return the changed fields, or `null` when a draft is invalid. */
function buildUpdate(
  drafts: Drafts,
  settings: LanguagarrSettings,
): LanguagarrSettingsUpdate | null {
  const update: LanguagarrSettingsUpdate = {}
  for (const field of TOGGLE_FIELDS) {
    if (drafts[field.key] !== settings[field.key]) {
      update[field.key] = drafts[field.key]
    }
  }
  for (const field of NUMERIC_FIELDS) {
    const value = Number(drafts[field.key])
    if (!Number.isInteger(value) || value < field.min || value > field.max) {
      return null
    }
    if (value !== settings[field.key]) update[field.key] = value
  }
  if (drafts.profiles.length === 0 || drafts.languages.length === 0) return null
  if (!sameSelection(drafts.profiles, settings.quality_profile_names)) {
    update.quality_profile_names = drafts.profiles
  }
  if (!sameSelection(drafts.languages, settings.target_audio_languages)) {
    update.target_audio_languages = drafts.languages
  }
  const linkUrl = parseLinkUrl(drafts.sonarr_link_url)
  if (linkUrl === null) return null
  if (linkUrl !== settings.sonarr_link_url) update.sonarr_link_url = linkUrl
  return update
}

interface SettingsFormProps {
  settings: LanguagarrSettings
  onSave: (update: LanguagarrSettingsUpdate) => void
  isPending: boolean
}

/** Form state is scoped to one known settings snapshot via the parent key. */
function SettingsForm({ settings, onSave, isPending }: SettingsFormProps) {
  const [drafts, setDrafts] = useState<Drafts>({
    enabled: settings.enabled,
    auto_queue: settings.auto_queue,
    monitored_only: settings.monitored_only,
    interval_minutes: String(settings.interval_minutes),
    searches_per_run: String(settings.searches_per_run),
    retry_after_hours: String(settings.retry_after_hours),
    profiles: settings.quality_profile_names,
    languages: settings.target_audio_languages,
    sonarr_link_url: settings.sonarr_link_url,
  })
  const update = buildUpdate(drafts, settings)
  const canSave = update !== null && Object.keys(update).length > 0

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <SettingsIcon className="size-4 text-muted-foreground" />
          Languagarr settings
        </CardTitle>
        <CardDescription>
          Scope, target languages and pacing of the replacement searches.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        {TOGGLE_FIELDS.map((field) => (
          <div
            key={field.key}
            className="flex items-start justify-between gap-4 rounded-md border p-3"
          >
            <div className="grid gap-1">
              <label
                htmlFor={`languagarr-${field.key}`}
                className="text-sm font-medium"
              >
                {field.label}
              </label>
              <p className="text-xs text-muted-foreground">{field.help}</p>
            </div>
            <Switch
              id={`languagarr-${field.key}`}
              checked={drafts[field.key]}
              onCheckedChange={(checked) =>
                setDrafts((current) => ({ ...current, [field.key]: checked }))
              }
              disabled={isPending}
              aria-label={field.label}
            />
          </div>
        ))}
        {NUMERIC_FIELDS.map((field) => (
          <div key={field.key} className="grid gap-2">
            <label
              htmlFor={`languagarr-${field.key}`}
              className="text-sm font-medium"
            >
              {field.label}
            </label>
            <Input
              id={`languagarr-${field.key}`}
              type="number"
              min={field.min}
              max={field.max}
              value={drafts[field.key]}
              onChange={(event) =>
                setDrafts((current) => ({
                  ...current,
                  [field.key]: event.target.value,
                }))
              }
              disabled={isPending}
            />
            <p className="text-xs text-muted-foreground">{field.help}</p>
          </div>
        ))}
        <LanguageChecklist
          selected={drafts.languages}
          onChange={(languages) =>
            setDrafts((current) => ({ ...current, languages }))
          }
          disabled={isPending}
        />
        <ProfileChecklist
          selected={drafts.profiles}
          onChange={(profiles) =>
            setDrafts((current) => ({ ...current, profiles }))
          }
          disabled={isPending}
        />
        <div className="grid gap-2">
          <label
            htmlFor="languagarr-sonarr-link-url"
            className="text-sm font-medium"
          >
            Sonarr link URL
          </label>
          <Input
            id="languagarr-sonarr-link-url"
            value={drafts.sonarr_link_url}
            onChange={(event) =>
              setDrafts((current) => ({
                ...current,
                sonarr_link_url: event.target.value,
              }))
            }
            placeholder="http://192.168.0.2:8989"
            disabled={isPending}
          />
          <p className="text-xs text-muted-foreground">
            Address your browser uses to open Sonarr, for the series links on
            the Review and Queue tabs. Leave empty to use the Sonarr service
            URL; a Docker hostname such as http://sonarr:8989 is swapped for the
            address you opened this app from, keeping the port.
          </p>
        </div>
        <div className="flex justify-end">
          <Button
            type="button"
            onClick={() => {
              // Only reachable when ``canSave`` holds, so ``update`` is non-null.
              onSave(update as LanguagarrSettingsUpdate)
            }}
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

/** Languagarr Settings tab. */
export function Settings() {
  const { data: settings, isLoading } = useLanguagarrSettings()
  const updateSettings = useUpdateLanguagarrSettings()

  if (isLoading || !settings) {
    return (
      <p className="text-sm text-muted-foreground">
        Loading Languagarr settings…
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
