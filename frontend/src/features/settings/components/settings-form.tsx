import { type ReactNode } from "react"

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
import { SettingsHelp } from "@/shared/components/settings-help"

/** A labelled form row with a saved/state hint. */
export function Field({
  label,
  hint,
  helpText,
  children,
}: {
  label: string
  hint: string
  helpText: ReactNode
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <label className="text-sm font-medium">{label}</label>
          <SettingsHelp label={label}>{helpText}</SettingsHelp>
        </div>
        <span className="text-xs text-muted-foreground">{hint}</span>
      </div>
      {children}
    </div>
  )
}

export function ActionWithHelp({
  label,
  helpText,
  children,
}: {
  label: string
  helpText: ReactNode
  children: ReactNode
}) {
  return (
    <div className="flex items-center gap-1.5">
      {children}
      <SettingsHelp label={label}>{helpText}</SettingsHelp>
    </div>
  )
}

/** Danger-zone action with a confirmation dialog. */
export function ClearAction({
  label,
  description,
  confirmLabel,
  helpText,
  disabled,
  onConfirm,
}: {
  label: string
  description: string
  confirmLabel: string
  helpText: ReactNode
  disabled: boolean
  onConfirm: () => void
}) {
  return (
    <ActionWithHelp label={label} helpText={helpText}>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="outline" disabled={disabled}>
            {label}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{label}?</AlertDialogTitle>
            <AlertDialogDescription>{description}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={onConfirm}>
              {confirmLabel}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ActionWithHelp>
  )
}
