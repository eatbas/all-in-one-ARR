import type { ReactNode } from "react"

import { CardAction } from "@/shared/components/ui/card"
import { Input } from "@/shared/components/ui/input"
import { Switch } from "@/shared/components/ui/switch"
import { Textarea } from "@/shared/components/ui/textarea"
import {
  NUMERIC_BOUNDS,
  type CleanarrDrafts,
  type DraftErrors,
  type NumericDraftKey,
  type TextDraftKey,
} from "@/features/cleanarr/settings-form"
import { cn } from "@/shared/lib/utils"

export type ToggleDraftKey = {
  [Key in keyof CleanarrDrafts]: CleanarrDrafts[Key] extends boolean
    ? Key
    : never
}[keyof CleanarrDrafts]

/** Draft state and its setter, shared by every field of the form. */
export interface FieldContext {
  drafts: CleanarrDrafts
  errors: DraftErrors
  disabled: boolean
  setDraft: <Key extends keyof CleanarrDrafts>(
    key: Key,
    value: CleanarrDrafts[Key],
  ) => void
}

function fieldId(key: string): string {
  return `cleanarr-${key.replaceAll("_", "-")}`
}

/** Label, control and hint; the hint becomes the error while invalid. */
export function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string
  label: string
  hint: string
  error?: string
  children: ReactNode
}) {
  return (
    <div className="grid content-start gap-2">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children}
      <p
        id={`${id}-hint`}
        className={cn(
          "text-xs",
          error ? "text-destructive" : "text-muted-foreground",
        )}
      >
        {error ?? hint}
      </p>
    </div>
  )
}

export function NumberField({
  context,
  name,
  label,
  hint,
}: {
  context: FieldContext
  name: NumericDraftKey
  label: string
  hint: string
}) {
  const id = fieldId(name)
  const [min, max] = NUMERIC_BOUNDS[name]
  return (
    <Field id={id} label={label} hint={hint} error={context.errors[name]}>
      <Input
        id={id}
        type="number"
        min={min}
        max={max}
        value={context.drafts[name]}
        aria-invalid={context.errors[name] ? true : undefined}
        aria-describedby={`${id}-hint`}
        disabled={context.disabled}
        onChange={(event) => context.setDraft(name, event.target.value)}
      />
    </Field>
  )
}

export function TextField({
  context,
  name,
  label,
  hint,
  rows,
  mono = false,
}: {
  context: FieldContext
  name: TextDraftKey
  label: string
  hint: string
  /** Render a textarea with this many rows; omit for a single-line input. */
  rows?: number
  mono?: boolean
}) {
  const id = fieldId(name)
  const shared = {
    id,
    value: context.drafts[name],
    "aria-invalid": context.errors[name] ? true : undefined,
    "aria-describedby": `${id}-hint`,
    disabled: context.disabled,
    className: cn(mono && "font-mono"),
  }
  return (
    <Field id={id} label={label} hint={hint} error={context.errors[name]}>
      {rows ? (
        <Textarea
          {...shared}
          rows={rows}
          onChange={(event) => context.setDraft(name, event.target.value)}
        />
      ) : (
        <Input
          {...shared}
          onChange={(event) => context.setDraft(name, event.target.value)}
        />
      )}
    </Field>
  )
}

/** A card-header on/off switch with its state label. */
export function HeaderSwitch({
  context,
  name,
  label,
}: {
  context: FieldContext
  name: ToggleDraftKey
  label: string
}) {
  const checked = context.drafts[name]
  return (
    <CardAction className="flex items-center gap-2">
      <span className="text-sm font-medium">{checked ? "On" : "Off"}</span>
      <Switch
        aria-label={label}
        checked={checked}
        disabled={context.disabled}
        onCheckedChange={(value) => context.setDraft(name, value)}
      />
    </CardAction>
  )
}
