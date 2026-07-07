import { SearchIcon } from "lucide-react"

import { Input } from "@/shared/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select"
import { ClearHistoryDialog } from "@/features/findarr/components/clear-history-dialog"
import type { FindarrAppName } from "@/shared/lib/api"

/** Page-size choices for the "Show" selector. */
const SHOW_OPTIONS = [10, 20, 50, 100] as const

/** Instance filter value: every instance, or one specific app. */
export type InstanceFilter = "all" | FindarrAppName

interface HistoryToolbarProps {
  instanceFilter: InstanceFilter
  onInstanceFilterChange: (value: InstanceFilter) => void
  search: string
  onSearchChange: (value: string) => void
  showCount: number
  onShowCountChange: (value: number) => void
  onClear: () => void
  isClearing: boolean
}

/** Filter, search, page-size, and clear controls above the history list. */
export function HistoryToolbar({
  instanceFilter,
  onInstanceFilterChange,
  search,
  onSearchChange,
  showCount,
  onShowCountChange,
  onClear,
  isClearing,
}: HistoryToolbarProps) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <Select
        value={instanceFilter}
        onValueChange={(value) =>
          onInstanceFilterChange(value as InstanceFilter)
        }
      >
        <SelectTrigger
          aria-label="Filter by instance"
          className="w-full sm:w-44"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All instances</SelectItem>
          <SelectItem value="sonarr">Sonarr</SelectItem>
          <SelectItem value="radarr">Radarr</SelectItem>
        </SelectContent>
      </Select>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full sm:w-56">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="Search history"
            placeholder="Search…"
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <span>Show</span>
          <Select
            value={String(showCount)}
            onValueChange={(value) => onShowCountChange(Number(value))}
          >
            <SelectTrigger aria-label="Rows to show" className="w-20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SHOW_OPTIONS.map((count) => (
                <SelectItem key={count} value={String(count)}>
                  {count}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <ClearHistoryDialog onConfirm={onClear} disabled={isClearing} />
      </div>
    </div>
  )
}
