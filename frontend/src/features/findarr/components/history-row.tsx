import { InfoIcon } from "lucide-react"

import { TableCell, TableRow } from "@/shared/components/ui/table"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip"
import { formatRelativeTime } from "@/shared/lib/format"
import { cn } from "@/shared/lib/utils"
import { processedInformation } from "@/features/findarr/components/history-format"
import type { FindarrAppName, FindarrHistoryEntry } from "@/shared/lib/api"

/** Single Sonarr/Radarr connection per app, so each maps to a "Default" instance. */
const INSTANCE_LABELS: Record<FindarrAppName, string> = {
  sonarr: "Sonarr - Default",
  radarr: "Radarr - Default",
}

interface OperationMeta {
  label: string
  className: string
}

/** Display label and pill colour for a history row's operation (its mode). */
function operationMeta(mode: FindarrHistoryEntry["mode"]): OperationMeta {
  switch (mode) {
    case "missing":
      return {
        label: "Missing",
        className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
      }
    case "upgrade":
      return {
        label: "Upgrade",
        className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
      }
    default:
      return { label: "System", className: "bg-muted text-muted-foreground" }
  }
}

interface HistoryRowProps {
  entry: FindarrHistoryEntry
}

/** One Findarr history row rendered across the five reference columns. */
export function HistoryRow({ entry }: HistoryRowProps) {
  const meta = operationMeta(entry.mode)
  const information = processedInformation(entry)
  return (
    <TableRow>
      <TableCell>
        <div className="flex min-w-0 items-center gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label={`Details for ${information}: ${entry.status}`}
                className={cn(
                  "inline-flex size-5 shrink-0 items-center justify-center rounded-full transition-colors",
                  entry.status === "error" ? "text-destructive" : "text-sky-500",
                )}
              >
                <InfoIcon className="size-4" aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent sideOffset={6} className="max-w-xs text-pretty">
              <span className="font-medium capitalize">{entry.status}</span>
              {/* System rows have no title, so their detail is already the cell
                  text — only append it to the tooltip when a title is shown. */}
              {entry.title === null ? "" : ` — ${entry.detail}`}
            </TooltipContent>
          </Tooltip>
          <span className="truncate max-w-[34ch] font-medium" title={information}>
            {information}
          </span>
        </div>
      </TableCell>
      <TableCell>
        <span
          className={cn(
            "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
            meta.className,
          )}
        >
          {meta.label}
        </span>
      </TableCell>
      <TableCell className="tabular-nums">{entry.item_id ?? "—"}</TableCell>
      <TableCell>{INSTANCE_LABELS[entry.app]}</TableCell>
      <TableCell className="whitespace-nowrap text-muted-foreground">
        {formatRelativeTime(entry.ts)}
      </TableCell>
    </TableRow>
  )
}
