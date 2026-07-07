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

interface ClearHistoryDialogProps {
  /** Invoked when the user confirms clearing the history log. */
  onConfirm: () => void
  /** Disables the trigger while a clear is pending. */
  disabled: boolean
}

/**
 * Confirmation dialog for emptying the Findarr history log. Distinct from
 * {@link FindarrResetDialog}: clearing history removes the audit log shown on
 * this tab, whereas reset clears processed-media bookkeeping. Neither touches
 * Sonarr/Radarr libraries.
 */
export function ClearHistoryDialog({
  onConfirm,
  disabled,
}: ClearHistoryDialogProps) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button size="sm" variant="destructive" disabled={disabled}>
          <Trash2Icon className="size-4" />
          Clear
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Clear Findarr history?</AlertDialogTitle>
          <AlertDialogDescription>
            This removes every recorded Findarr history entry. It does not
            change Sonarr or Radarr, nor Findarr&apos;s processed state.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>
            Clear history
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
