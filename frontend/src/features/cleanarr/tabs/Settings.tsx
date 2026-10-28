import { useState, type ReactNode } from "react"
import { SaveIcon } from "lucide-react"

import { SettingsHelp } from "@/shared/components/settings-help"
import { Button } from "@/shared/components/ui/button"
import {
  Card,
  CardAction,
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
import {
  Field,
  HeaderSwitch,
  NumberField,
  TextField,
  type FieldContext,
} from "@/features/cleanarr/components/settings-fields"
import {
  isDirty,
  toDrafts,
  validateDrafts,
  type CleanarrDrafts,
  type PatternMode,
} from "@/features/cleanarr/settings-form"
import type { CleanarrSettings, CleanarrSettingsUpdate } from "@/shared/lib/api"
import {
  useCleanarrSettings,
  useUpdateCleanarrSettings,
} from "@/shared/lib/queries"

function SchedulerCard({ context }: { context: FieldContext }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Cleanarr scheduler</CardTitle>
        <CardAction className="flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium">Enabled</span>
            <SettingsHelp label="Enable Cleanarr">
              Allows the scheduler to strike and clean stuck Sonarr/Radarr queue
              items.
            </SettingsHelp>
          </div>
          <Switch
            aria-label="Enable Cleanarr"
            checked={context.drafts.enabled}
            disabled={context.disabled}
            onCheckedChange={(value) => context.setDraft("enabled", value)}
          />
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-4 rounded-md border border-amber-500/40 bg-amber-50 p-3 dark:bg-amber-950/30">
          <div className="grid gap-1">
            <label htmlFor="cleanarr-dry-run" className="text-sm font-medium">
              Dry run
            </label>
            <p className="text-xs text-muted-foreground">
              No changes are made. Strikes are counted and History shows what
              Cleanarr would remove, delete or quarantine. Turn this off only
              after Cleanuparr&apos;s Queue Cleaner, Malware Blocker and orphan
              handling are disabled.
            </p>
          </div>
          <Switch
            id="cleanarr-dry-run"
            aria-label="Dry run"
            checked={context.drafts.dry_run}
            disabled={context.disabled}
            onCheckedChange={(value) => context.setDraft("dry_run", value)}
          />
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <NumberField
            context={context}
            name="interval_minutes"
            label="Interval (minutes)"
            hint="How often Cleanarr checks the queues. 5–1440 minutes."
          />
          <NumberField
            context={context}
            name="max_strikes"
            label="Max strikes"
            hint="Runs an item must stay stuck before it is removed and blocklisted. 3–20."
          />
          <NumberField
            context={context}
            name="max_removals_per_run"
            label="Removal cap"
            hint="Most removals per run across Sonarr and Radarr. Items over the cap keep their strikes. 1–50."
          />
        </div>
      </CardContent>
    </Card>
  )
}

function QueueCard({ context }: { context: FieldContext }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Queue cleaning</CardTitle>
        <CardDescription>
          Strikes usenet items that fail to import or whose SABnzbd job failed.
        </CardDescription>
        <HeaderSwitch
          context={context}
          name="queue_enabled"
          label="Enable queue cleaning"
        />
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        <Field
          id="cleanarr-pattern-mode"
          label="Pattern mode"
          hint="Applies to failed imports only. Include mode strikes only items whose message matches a pattern."
        >
          <Select
            value={context.drafts.pattern_mode}
            disabled={context.disabled}
            onValueChange={(value) =>
              context.setDraft("pattern_mode", value as PatternMode)
            }
          >
            <SelectTrigger id="cleanarr-pattern-mode" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="exclude">
                Exclude: strike unless a message matches
              </SelectItem>
              <SelectItem value="include">
                Include: strike only when a message matches
              </SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <TextField
          context={context}
          name="patterns"
          label="Patterns"
          rows={4}
          hint="One per line, up to 50. Matched case-insensitively against the import messages and title (plain text, not regular expressions)."
        />
      </CardContent>
    </Card>
  )
}

function FilePassCards({ context }: { context: FieldContext }) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Malware blocker</CardTitle>
          <CardDescription>
            Deletes blocked-extension files from completed SABnzbd jobs that
            Sonarr/Radarr have not imported yet.
          </CardDescription>
          <HeaderSwitch
            context={context}
            name="malware_enabled"
            label="Enable malware blocker"
          />
        </CardHeader>
        <CardContent>
          <TextField
            context={context}
            name="extensions"
            label="Blocked extensions"
            rows={3}
            hint="Separated by spaces or new lines, up to 100. Only these files are deleted; media files are never touched."
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Orphan quarantine</CardTitle>
          <CardDescription>
            Moves folders in SABnzbd&apos;s completed folder that nothing refers
            to into the quarantine folder, then purges them later.
          </CardDescription>
          <HeaderSwitch
            context={context}
            name="orphans_enabled"
            label="Enable orphan quarantine"
          />
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <NumberField
            context={context}
            name="min_age_hours"
            label="Minimum age (hours)"
            hint="Entries younger than this are left alone. 1–720."
          />
          <NumberField
            context={context}
            name="quarantine_retention_days"
            label="Keep in quarantine (days)"
            hint="Quarantined entries are deleted after this. 1–365."
          />
        </CardContent>
      </Card>
    </div>
  )
}

function PathsCard({ context }: { context: FieldContext }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Paths</CardTitle>
        <CardDescription>
          Mount SABnzbd&apos;s completed folder read-write into the aio-arr
          container. The quarantine folder must be inside it, on the same
          filesystem: Cleanarr moves entries and never copies them between
          filesystems.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        <TextField
          context={context}
          name="completed_root"
          label="Completed folder"
          mono
          hint="Where SABnzbd's completed folder is mounted in this container. Absolute path."
        />
        <TextField
          context={context}
          name="quarantine_dir"
          label="Quarantine folder"
          mono
          hint="Must be inside the completed folder. Created on first use."
        />
      </CardContent>
    </Card>
  )
}

const APP_CARDS = [
  { name: "sonarr_enabled", label: "Sonarr" },
  { name: "radarr_enabled", label: "Radarr" },
] as const

function AppCards({ context }: { context: FieldContext }) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {APP_CARDS.map((app) => (
        <Card key={app.name}>
          <CardHeader className="items-center">
            <CardTitle>{app.label}</CardTitle>
            <CardAction className="flex items-center gap-2">
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-medium">Process app</span>
                <SettingsHelp label={`Process ${app.label}`}>
                  {`Includes ${app.label}'s queue in Cleanarr processing.`}
                </SettingsHelp>
              </div>
              <Switch
                aria-label={`Enable ${app.label}`}
                checked={context.drafts[app.name]}
                disabled={context.disabled}
                onCheckedChange={(value) => context.setDraft(app.name, value)}
              />
            </CardAction>
          </CardHeader>
        </Card>
      ))}
    </div>
  )
}

function IgnoreCard({
  context,
  footer,
}: {
  context: FieldContext
  footer: ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Ignore lists</CardTitle>
        <CardDescription>
          Cleanarr never strikes, removes, deletes or quarantines anything that
          matches. One entry per line, up to 500 per list.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-4 md:grid-cols-3">
          <TextField
            context={context}
            name="ignore_download_ids"
            label="Download IDs"
            rows={4}
            mono
            hint="Exact SABnzbd job IDs. The Queue tab's Ignore button adds them here."
          />
          <TextField
            context={context}
            name="ignore_categories"
            label="Categories"
            rows={4}
            hint="Exact SABnzbd category names."
          />
          <TextField
            context={context}
            name="ignore_title_contains"
            label="Title contains"
            rows={4}
            hint="Case-insensitive text in the release title."
          />
        </div>
        {footer}
      </CardContent>
    </Card>
  )
}

interface SettingsFormProps {
  settings: CleanarrSettings
  onSave: (update: CleanarrSettingsUpdate) => void
  isPending: boolean
}

/** Form state is scoped to one known settings snapshot via the parent key. */
function SettingsForm({ settings, onSave, isPending }: SettingsFormProps) {
  const [drafts, setDrafts] = useState<CleanarrDrafts>(() => toDrafts(settings))
  const { update, errors } = validateDrafts(drafts)
  const canSave = update !== null && isDirty(update, settings)
  const context: FieldContext = {
    drafts,
    errors,
    disabled: isPending,
    setDraft: (key, value) =>
      setDrafts((current) => ({ ...current, [key]: value })),
  }

  return (
    <div className="flex flex-col gap-6">
      <SchedulerCard context={context} />
      <QueueCard context={context} />
      <FilePassCards context={context} />
      <PathsCard context={context} />
      <AppCards context={context} />
      <IgnoreCard
        context={context}
        footer={
          <div className="flex justify-end">
            <Button
              type="button"
              onClick={() => {
                // Only reachable when ``canSave`` holds, so ``update`` is non-null.
                onSave(update as CleanarrSettingsUpdate)
              }}
              disabled={!canSave || isPending}
            >
              <SaveIcon className="size-4" />
              Save
            </Button>
          </div>
        }
      />
    </div>
  )
}

/** Cleanarr Settings tab: one draft for every section and a single Save. */
export function Settings() {
  const { data: settings, isLoading, isError, error } = useCleanarrSettings()
  const updateSettings = useUpdateCleanarrSettings()

  if (isError) {
    return (
      <p className="text-sm text-destructive">
        Could not load Cleanarr settings: {error.message}
      </p>
    )
  }
  if (isLoading || !settings) {
    return (
      <p className="text-sm text-muted-foreground">
        Loading Cleanarr settings…
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
