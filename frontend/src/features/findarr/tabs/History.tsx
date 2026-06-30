import { useState } from "react"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table"
import { HistoryRow } from "@/features/findarr/components/history-row"
import { HistoryPagination } from "@/features/findarr/components/history-pagination"
import { pageCount } from "@/features/findarr/components/history-pagination-utils"
import { processedInformation } from "@/features/findarr/components/history-format"
import {
  HistoryToolbar,
  type InstanceFilter,
} from "@/features/findarr/components/history-toolbar"
import {
  useClearFindarrHistory,
  useFindarrHistory,
} from "@/shared/lib/queries"

export function History() {
  const { data: history, isLoading } = useFindarrHistory()
  const clearHistory = useClearFindarrHistory()
  const [instanceFilter, setInstanceFilter] = useState<InstanceFilter>("all")
  const [search, setSearch] = useState("")
  const [pageSize, setPageSize] = useState(20)
  const [page, setPage] = useState(1)

  if (isLoading || !history) {
    return <p className="text-sm text-muted-foreground">Loading history…</p>
  }
  if (history.length === 0) {
    return <p className="text-sm text-muted-foreground">No Findarr history yet.</p>
  }

  const query = search.trim().toLowerCase()
  const filtered = history
    .filter((entry) => instanceFilter === "all" || entry.app === instanceFilter)
    .filter(
      (entry) =>
        query === "" || processedInformation(entry).toLowerCase().includes(query),
    )

  // Clamp the page so a filter that shrinks the result set never strands the
  // user on a now-empty page, even before the reset-on-change handlers fire.
  const totalPages = pageCount(filtered.length, pageSize)
  const currentPage = Math.min(page, totalPages)
  const visible = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize)

  return (
    <div className="flex flex-col gap-4">
      <HistoryToolbar
        instanceFilter={instanceFilter}
        onInstanceFilterChange={(value) => {
          setInstanceFilter(value)
          setPage(1)
        }}
        search={search}
        onSearchChange={(value) => {
          setSearch(value)
          setPage(1)
        }}
        showCount={pageSize}
        onShowCountChange={(value) => {
          setPageSize(value)
          setPage(1)
        }}
        onClear={() => clearHistory.mutate()}
        isClearing={clearHistory.isPending}
      />

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-xs uppercase tracking-wider">
                Processed information
              </TableHead>
              <TableHead className="text-xs uppercase tracking-wider">Operation</TableHead>
              <TableHead className="text-xs uppercase tracking-wider">ID number</TableHead>
              <TableHead className="text-xs uppercase tracking-wider">
                Name of instance
              </TableHead>
              <TableHead className="text-xs uppercase tracking-wider">How long ago</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className="text-center text-sm text-muted-foreground"
                >
                  No entries match your filters.
                </TableCell>
              </TableRow>
            ) : (
              visible.map((entry) => <HistoryRow key={entry.id} entry={entry} />)
            )}
          </TableBody>
        </Table>
      </div>

      {filtered.length > 0 && (
        <HistoryPagination
          page={currentPage}
          pageSize={pageSize}
          totalItems={filtered.length}
          onPageChange={setPage}
        />
      )}
    </div>
  )
}
