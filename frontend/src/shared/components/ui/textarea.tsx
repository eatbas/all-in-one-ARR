import * as React from "react"

import { cn } from "@/shared/lib/utils"

/** Multi-line text field styled like {@link Input}. */
function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      data-lpignore="true"
      data-1p-ignore="true"
      data-bwignore="true"
      autoComplete="off"
      className={cn(
        "flex min-h-16 w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive dark:bg-input/30",
        className,
      )}
      {...props}
    />
  )
}

export { Textarea }
