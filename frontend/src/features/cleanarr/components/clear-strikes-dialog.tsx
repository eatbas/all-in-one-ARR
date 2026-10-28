import { XCircleIcon } from "lucide-react"

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

interface ClearStrikesDialogProps {
  /** Strikes the reset would delete, named in the confirmation. */
  total: number
  onConfirm: () => void
  disabled: boolean
}

/** Destructive "Clear strikes" button behind a confirmation dialog. */
export function ClearStrikesDialog({
  total,
  onConfirm,
  disabled,
}: ClearStrikesDialogProps) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button size="sm" variant="destructive" disabled={disabled}>
          <XCircleIcon className="size-4" />
          Clear strikes
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Clear all Cleanarr strikes?</AlertDialogTitle>
          <AlertDialogDescription>
            This deletes all {total} strikes, so every stuck item starts again
            from 0 on the next run. Nothing is removed from Sonarr, Radarr or
            SABnzbd.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>
            Clear strikes
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
