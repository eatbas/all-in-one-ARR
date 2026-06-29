import type { ReactNode } from "react"
import { RotateCcwIcon } from "lucide-react"

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

interface FindarrResetDialogProps {
  /** Text on the destructive trigger button (e.g. "Reset", "Emergency reset"). */
  triggerLabel: string
  /** Body copy explaining what the reset does for this entry point. */
  description: ReactNode
  /** Invoked when the user confirms the reset. */
  onConfirm: () => void
  /** Disables the trigger while a reset (or related action) is pending. */
  disabled: boolean
}

/**
 * Shared confirmation dialog for clearing Findarr processed state. Used by the
 * Status tab ("Reset") and the Settings tab stateful-management card
 * ("Emergency reset"); both clear processed-media ids only and never touch media
 * or Arr libraries.
 */
export function FindarrResetDialog({
  triggerLabel,
  description,
  onConfirm,
  disabled,
}: FindarrResetDialogProps) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button size="sm" variant="destructive" disabled={disabled}>
          <RotateCcwIcon className="size-4" />
          {triggerLabel}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Reset Findarr processed state?</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>Reset</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
