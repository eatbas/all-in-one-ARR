import { InfoIcon } from "lucide-react"
import type { ReactNode } from "react"

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip"
import { cn } from "@/shared/lib/utils"

type SettingsHelpProps = {
  label: string
  children: ReactNode
  className?: string
}

/** Icon-only help trigger for settings controls and actions. */
export function SettingsHelp({ label, children, className }: SettingsHelpProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={`Explain ${label}`}
          className={cn(
            "inline-flex size-6 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            className,
          )}
        >
          <InfoIcon className="size-4" aria-hidden="true" />
        </button>
      </TooltipTrigger>
      <TooltipContent sideOffset={6} className="max-w-xs text-pretty">
        {children}
      </TooltipContent>
    </Tooltip>
  )
}
