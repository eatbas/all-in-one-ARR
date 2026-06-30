import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react"

import { Button } from "@/shared/components/ui/button"
import { pageCount } from "@/features/findarr/components/history-pagination-utils"

interface HistoryPaginationProps {
  /** Current 1-based page. */
  page: number
  /** Rows shown per page. */
  pageSize: number
  /** Total number of filtered rows across every page. */
  totalItems: number
  /** Requests a move to the given 1-based page. */
  onPageChange: (page: number) => void
}

/**
 * Presentational pager rendered beneath the history table. The parent owns the
 * page state and the row slicing; this component only reports the visible range,
 * the page position, and Previous/Next intent. It clamps nothing itself — the
 * parent passes an already-clamped {@link HistoryPaginationProps.page}.
 */
export function HistoryPagination({
  page,
  pageSize,
  totalItems,
  onPageChange,
}: HistoryPaginationProps) {
  const totalPages = pageCount(totalItems, pageSize)
  const start = totalItems === 0 ? 0 : (page - 1) * pageSize + 1
  const end = Math.min(page * pageSize, totalItems)

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-sm text-muted-foreground">
        Showing {start}–{end} of {totalItems}
      </p>
      <div className="flex items-center gap-3">
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label="Previous page"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeftIcon className="size-4" />
          Previous
        </Button>
        <span className="text-sm text-muted-foreground">
          Page {page} of {totalPages}
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label="Next page"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Next
          <ChevronRightIcon className="size-4" />
        </Button>
      </div>
    </div>
  )
}
