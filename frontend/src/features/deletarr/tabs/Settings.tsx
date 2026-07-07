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
import type { DeletarrSettings, DeletarrSettingsUpdate } from "@/shared/lib/api"
import {
  useDeletarrSettings,
  useUpdateDeletarrSettings,
} from "@/shared/lib/queries"

interface SettingsFormProps {
  settings: DeletarrSettings
  onSave: (update: DeletarrSettingsUpdate) => void
  isPending: boolean
}

/** Form state is scoped to one known settings snapshot via the parent key. */
function SettingsForm({ settings, onSave, isPending }: SettingsFormProps) {
  const [drafts, setDrafts] = useState({
    movies_path: settings.movies_path,
    tv_path: settings.tv_path,
    use_arr_source: settings.use_arr_source,
  })

  const moviesChanged = drafts.movies_path.trim() !== settings.movies_path
  const tvChanged = drafts.tv_path.trim() !== settings.tv_path
  const arrSourceChanged = drafts.use_arr_source !== settings.use_arr_source
  const hasChanges = moviesChanged || tvChanged || arrSourceChanged
  const canSave =
    hasChanges &&
    (!moviesChanged || drafts.movies_path.trim() !== "") &&
    (!tvChanged || drafts.tv_path.trim() !== "")

  function handleSave() {
    const update: DeletarrSettingsUpdate = {}
    if (moviesChanged) {
      update.movies_path = drafts.movies_path.trim()
    }
    if (tvChanged) {
      update.tv_path = drafts.tv_path.trim()
    }
    if (arrSourceChanged) {
      update.use_arr_source = drafts.use_arr_source
    }
    // Save is only reachable when ``canSave`` holds, which requires at least one
    // changed field, so ``update`` is always non-empty here.
    onSave(update)
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Deletarr Settings
        </h1>
        <p className="text-sm text-muted-foreground">
          Configure the library roots Deletarr scans for junk candidates.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <SettingsIcon className="size-4 text-muted-foreground" />
            Media library paths
          </CardTitle>
          <CardDescription>
            Changes are saved to the settings store and take effect on the next
            scan.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5">
          <div className="grid gap-2">
            <label
              htmlFor="deletarr-movies-path"
              className="text-sm font-medium"
            >
              Movies path
            </label>
            <Input
              id="deletarr-movies-path"
              value={drafts.movies_path}
              onChange={(event) =>
                setDrafts((current) => ({
                  ...current,
                  movies_path: event.target.value,
                }))
              }
              placeholder="/media/movies"
              disabled={isPending}
            />
          </div>
          <div className="grid gap-2">
            <label htmlFor="deletarr-tv-path" className="text-sm font-medium">
              TV path
            </label>
            <Input
              id="deletarr-tv-path"
              value={drafts.tv_path}
              onChange={(event) =>
                setDrafts((current) => ({
                  ...current,
                  tv_path: event.target.value,
                }))
              }
              placeholder="/media/tv"
              disabled={isPending}
            />
          </div>
          <div className="flex items-start justify-between gap-4 rounded-md border p-3">
            <div className="grid gap-1">
              <label
                htmlFor="deletarr-use-arr-source"
                className="text-sm font-medium"
              >
                Use Radarr and Sonarr as the source of truth
              </label>
              <p className="text-xs text-muted-foreground">
                When on, only files your library manager does not track are
                flagged; Deletarr falls back to the heuristic scan when they are
                unreachable.
              </p>
            </div>
            <Switch
              id="deletarr-use-arr-source"
              checked={drafts.use_arr_source}
              onCheckedChange={(checked) =>
                setDrafts((current) => ({
                  ...current,
                  use_arr_source: checked,
                }))
              }
              disabled={isPending}
              aria-label="Use Radarr and Sonarr as the source of truth"
            />
          </div>
          <div className="flex justify-end">
            <Button
              type="button"
              onClick={handleSave}
              disabled={!canSave || isPending}
            >
              <SaveIcon className="size-4" />
              Save
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/** Deletarr Settings tab: edit the Movies and TV library roots. */
export function Settings() {
  const { data: settings, isLoading } = useDeletarrSettings()
  const updateSettings = useUpdateDeletarrSettings()

  if (isLoading || !settings) {
    return (
      <p className="text-sm text-muted-foreground">
        Loading Deletarr settings…
      </p>
    )
  }

  return (
    <SettingsForm
      key={`${settings.movies_path}|${settings.tv_path}|${String(settings.use_arr_source)}`}
      settings={settings}
      onSave={(update) => updateSettings.mutate(update)}
      isPending={updateSettings.isPending}
    />
  )
}
