import { RefreshCwIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { DryRunSwitch } from "@/components/dry-run-switch"
import { ModeToggle } from "@/components/mode-toggle"
import { cn } from "@/lib/utils"
import { useStatus, useSyncNow } from "@/lib/queries"

/** Pill showing whether the backend currently holds a valid Trakt token. */
function TraktStatusPill({ connected }: { connected: boolean }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1.5",
        connected
          ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
          : "border-amber-500/40 text-amber-600 dark:text-amber-400",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          connected ? "bg-emerald-500" : "bg-amber-500",
        )}
        aria-hidden
      />
      {connected ? "Trakt connected" : "Trakt needs auth"}
    </Badge>
  )
}

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
  const traktConnected = status?.trakt_connected ?? false

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60 md:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <span className="truncate text-lg font-semibold tracking-tight">
          All-in-One ARR
        </span>
        <TraktStatusPill connected={traktConnected} />
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
