import type { ReactNode } from "react"

import { Checkbox } from "@/shared/components/ui/checkbox"

/** One choice in a {@link CheckboxGroup}. */
export interface CheckboxOption {
  value: string
  label: string
  /** Warning shown beside the label, e.g. for a saved value no longer offered. */
  warning?: string
}

interface CheckboxGroupProps {
  /** Unique prefix for the group's element ids. */
  id: string
  label: string
  options: CheckboxOption[]
  /** Checked values, in the order they were picked. */
  selected: string[]
  onChange: (next: string[]) => void
  disabled: boolean
  /** Most values that may be checked; further boxes are locked at the limit. */
  max: number
  /** Status line under the list (loading, error, empty), if any. */
  notice?: string | null
  help: ReactNode
}

/**
 * A labelled checklist for picking several values (Languagarr's quality
 * profiles and target languages). Exposed as an ARIA group named by `label`, so
 * each checkbox is reachable by its own option label.
 */
export function CheckboxGroup({
  id,
  label,
  options,
  selected,
  onChange,
  disabled,
  max,
  notice,
  help,
}: CheckboxGroupProps) {
  const atLimit = selected.length >= max
  const labelId = `${id}-label`

  function toggle(value: string, checked: boolean) {
    onChange(
      checked
        ? [...selected, value]
        : selected.filter((current) => current !== value),
    )
  }

  return (
    <div role="group" aria-labelledby={labelId} className="grid gap-2">
      <span id={labelId} className="text-sm font-medium">
        {label}
      </span>
      {options.length > 0 && (
        <ul className="grid gap-2 rounded-md border p-3 sm:grid-cols-2">
          {options.map((option, index) => {
            const optionId = `${id}-${index}`
            const checked = selected.includes(option.value)
            return (
              <li key={option.value} className="flex items-center gap-2">
                <Checkbox
                  id={optionId}
                  checked={checked}
                  onCheckedChange={(state) =>
                    toggle(option.value, state === true)
                  }
                  disabled={disabled || (!checked && atLimit)}
                />
                <label htmlFor={optionId} className="text-sm">
                  {option.label}
                  {option.warning && (
                    <span className="ml-1.5 text-xs text-destructive">
                      ({option.warning})
                    </span>
                  )}
                </label>
              </li>
            )
          })}
        </ul>
      )}
      {notice && <p className="text-xs text-muted-foreground">{notice}</p>}
      <p className="text-xs text-muted-foreground">{help}</p>
    </div>
  )
}
