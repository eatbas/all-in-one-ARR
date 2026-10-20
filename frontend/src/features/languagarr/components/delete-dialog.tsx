import { Trash2Icon } from "lucide-react"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/components/ui/alert-dialog"
import { Button } from "@/shared/components/ui/button"
import { LANGUAGARR_MAX_DELETE, type LanguagarrItem } from "@/shared/lib/api"

interface DeleteDialogProps {
  /** The selected files, in display order. */
  items: LanguagarrItem[]
  /** Disables the trigger while another action is pending. */
  disabled: boolean
  /** Invoked when the user confirms the delete. */
  onConfirm: () => void
  /** Target languages as prose, e.g. "English or Turkish". */
  languagesLabel: string
}

/**
 * Confirmation for the destructive Delete & search action. The trigger is only
 * enabled for 1–25 selected files (the backend cap), and the dialog lists every
 * file and states that Sonarr deletes permanently unless its Recycle Bin is set.
 */
export function DeleteDialog({
  items,
  disabled,
  onConfirm,
  languagesLabel,
}: DeleteDialogProps) {
  const tooMany = items.length > LANGUAGARR_MAX_DELETE
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          type="button"
          variant="destructive"
          disabled={disabled || items.length === 0 || tooMany}
          title={
            tooMany
              ? `Select at most ${LANGUAGARR_MAX_DELETE} files to delete at once`
              : undefined
          }
        >
          <Trash2Icon className="size-4" />
          Delete & search ({items.length})
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            Delete {items.length} file(s) and search for replacements?
          </AlertDialogTitle>
          <AlertDialogDescription>
            Sonarr deletes each file, then searches its episodes for a release
            with {languagesLabel} audio. Each file is re-checked first and
            skipped if it changed since the scan. Deletion is permanent unless a
            Sonarr Recycle Bin is configured, and an episode stays missing if no
            compliant release exists.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <ul className="max-h-48 overflow-y-auto rounded-md border p-2 font-mono text-xs">
          {items.map((item) => (
            <li key={item.episode_file_id} className="truncate">
              {`${item.series_title} — ${item.episode_label} (${item.audio_languages})`}
            </li>
          ))}
        </ul>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>
            Delete & search
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
