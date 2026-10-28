import { FlaskConicalIcon } from "lucide-react"

import { Badge } from "@/shared/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table"
import {
  actionMeta,
  historyDetail,
  PILL_BASE,
  PILL_STYLES,
  sourceLabel,
} from "@/features/cleanarr/labels"
import { formatRelativeTime, formatTimestamp } from "@/shared/lib/format"
import { useCleanarrHistory } from "@/shared/lib/queries"
import { cn } from "@/shared/lib/utils"

/** Cleanarr History tab: removals, file actions and dry-run reports. */
export function History() {
  const { data: history, isLoading, isError, error } = useCleanarrHistory()

  if (isError) {
    return (
      <p className="text-sm text-destructive">
        Could not load history: {error.message}
      </p>
    )
  }
  if (isLoading || !history) {
    return <p className="text-sm text-muted-foreground">Loading history…</p>
  }
  if (history.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No Cleanarr history yet.</p>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Time</TableHead>
          <TableHead>App</TableHead>
          <TableHead>Action</TableHead>
          <TableHead>Title</TableHead>
          <TableHead>Detail</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {history.map((entry) => {
          const meta = actionMeta(entry.action)
          return (
            <TableRow key={entry.id}>
              <TableCell
                className="whitespace-nowrap text-muted-foreground"
                title={formatTimestamp(entry.ts)}
              >
                {formatRelativeTime(entry.ts)}
              </TableCell>
              <TableCell>{sourceLabel(entry.app)}</TableCell>
              <TableCell>
                <div className="flex items-center gap-1.5">
                  <span className={cn(PILL_BASE, PILL_STYLES[meta.tone])}>
                    {meta.label}
                  </span>
                  {entry.dry_run ? (
                    <Badge variant="outline">
                      <FlaskConicalIcon aria-hidden="true" />
                      Dry run
                    </Badge>
                  ) : null}
                </div>
              </TableCell>
              <TableCell>
                <span
                  className="block max-w-[40ch] truncate font-medium"
                  title={entry.title ?? undefined}
                >
                  {entry.title ?? "—"}
                </span>
              </TableCell>
              <TableCell className="text-muted-foreground">
                {historyDetail(entry.action, entry.detail)}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
