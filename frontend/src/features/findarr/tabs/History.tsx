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
  const [showCount, setShowCount] = useState(20)

  if (isLoading || !history) {
    return <p className="text-sm text-muted-foreground">Loading history…</p>
  }
  if (history.length === 0) {
    return <p className="text-sm text-muted-foreground">No Findarr history yet.</p>
  }

  const query = search.trim().toLowerCase()
  const visible = history
    .filter((entry) => instanceFilter === "all" || entry.app === instanceFilter)
    .filter(
      (entry) =>
        query === "" || processedInformation(entry).toLowerCase().includes(query),
    )
    .slice(0, showCount)

  return (
    <div className="flex flex-col gap-4">
      <HistoryToolbar
        instanceFilter={instanceFilter}
        onInstanceFilterChange={setInstanceFilter}
        search={search}
        onSearchChange={setSearch}
        showCount={showCount}
        onShowCountChange={setShowCount}
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
    </div>
  )
}
