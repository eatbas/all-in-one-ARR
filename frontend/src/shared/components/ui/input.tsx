import * as React from "react"

import { cn } from "@/shared/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    // Wrap the control in a `position: relative` span. Every input here is a
    // config/secret field (API keys, URLs, the Trakt secret), not a website
    // login, so password-manager extensions (LastPass, 1Password, Bitwarden)
    // should leave them alone — the `data-*ignore` hints below request that.
    // When a manager ignores the hints and decorates the field anyway, it needs
    // a positioned ancestor to anchor its in-field icon as an overlay; without
    // one it inserts the icon into normal flow, which adds height to the field
    // and shoves the fields below it down (the cramped, shifting layout). This
    // wrapper is that anchor, so any injected icon overlays the field instead of
    // reflowing the page. `w-full min-w-0` keeps the previous sizing — full
    // width in a column, shrinkable when sharing a flex row with a button.
    <span data-slot="input-wrapper" className="relative block w-full min-w-0">
      <input
        type={type}
        data-slot="input"
        data-lpignore="true"
        data-1p-ignore="true"
        data-bwignore="true"
        data-form-type="other"
        autoComplete="off"
        className={cn(
          "flex h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30",
          className,
        )}
        {...props}
      />
    </span>
  )
}

export { Input }
