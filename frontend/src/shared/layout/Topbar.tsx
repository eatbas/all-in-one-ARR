import { RefreshCwIcon } from "lucide-react"

import { Badge } from "@/shared/components/ui/badge"
import { Button } from "@/shared/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip"
import { DryRunSwitch } from "@/shared/components/dry-run-switch"
import { ModeToggle } from "@/shared/components/mode-toggle"
import { cn } from "@/shared/lib/utils"
import { useStatus, useSyncNow } from "@/shared/lib/queries"

/**
 * Prominent dry-run indicator. Orange/warning styling whenever dry-run is ON to
 * make it unmistakable that side effects are being suppressed.
 */
function DryRunBadge({ dryRun }: { dryRun: boolean }) {
  if (dryRun) {
    return (
      <Badge className="border-transparent bg-orange-500 text-white hover:bg-orange-500/90 dark:bg-orange-600">
        DRY_RUN ON
      </Badge>
    )
  }
  return (
    <Badge
      variant="outline"
      className="border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
    >
      LIVE
    </Badge>
  )
}

/** Top application bar: branding, status indicators, and global actions. */
export function Topbar() {
  const { data: status } = useStatus()
  const syncNow = useSyncNow()

  const dryRun = status?.dry_run ?? true

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60 md:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <span className="truncate text-lg font-semibold tracking-tight">
          All-in-One ARR
        </span>
        <DryRunBadge dryRun={dryRun} />
      </div>

      <div className="ml-auto flex items-center gap-3">
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex items-center gap-2">
              <DryRunSwitch id="dry-run-switch" />
              <label
                htmlFor="dry-run-switch"
                className="hidden cursor-pointer text-sm text-muted-foreground sm:inline"
              >
                Dry-run
              </label>
            </div>
          </TooltipTrigger>
          <TooltipContent>
            When on, requests and removals are only logged, never executed.
          </TooltipContent>
        </Tooltip>

        <Button
          size="sm"
          onClick={() => syncNow.mutate()}
          disabled={syncNow.isPending}
        >
          <RefreshCwIcon
            className={cn("size-4", syncNow.isPending && "animate-spin")}
          />
          Sync now
        </Button>

        <ModeToggle />
      </div>
    </header>
  )
}
