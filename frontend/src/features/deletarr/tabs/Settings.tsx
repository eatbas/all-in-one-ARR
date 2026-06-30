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
  })

  const moviesChanged = drafts.movies_path.trim() !== settings.movies_path
  const tvChanged = drafts.tv_path.trim() !== settings.tv_path
  const hasChanges = moviesChanged || tvChanged
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
    if (Object.keys(update).length > 0) {
      onSave(update)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Deletarr Settings</h1>
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
            Changes are saved to the settings store and take effect on the next scan.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5">
          <div className="grid gap-2">
            <label htmlFor="deletarr-movies-path" className="text-sm font-medium">
              Movies path
            </label>
            <Input
              id="deletarr-movies-path"
              value={drafts.movies_path}
              onChange={(event) =>
                setDrafts((current) => ({ ...current, movies_path: event.target.value }))
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
                setDrafts((current) => ({ ...current, tv_path: event.target.value }))
              }
              placeholder="/media/tv"
              disabled={isPending}
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
    return <p className="text-sm text-muted-foreground">Loading Deletarr settings…</p>
  }

  return (
    <SettingsForm
      key={`${settings.movies_path}|${settings.tv_path}`}
      settings={settings}
      onSave={(update) => updateSettings.mutate(update)}
      isPending={updateSettings.isPending}
    />
  )
}
