import { PlayIcon, XCircleIcon } from "lucide-react"

import { SonarrSeriesLink } from "@/features/languagarr/components/sonarr-series-link"
import { useSonarrLinkBase } from "@/features/languagarr/sonarr-link"
import { StatBlock } from "@/shared/components/stat-block"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/components/ui/alert-dialog"
import { Badge } from "@/shared/components/ui/badge"
import { Button } from "@/shared/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table"
import type { LanguagarrQueueRow } from "@/shared/lib/api"
import { formatTimestamp } from "@/shared/lib/format"
import {
  useClearLanguagarrPending,
  useLanguagarrQueue,
  useLanguagarrStatus,
  useRunLanguagarr,
} from "@/shared/lib/queries"
import {
  QUEUE_LABELS,
  VERDICT_LABELS,
} from "@/features/languagarr/review-groups"

const STATUS_VARIANTS: Record<
  LanguagarrQueueRow["status"],
  "secondary" | "outline" | "destructive"
> = {
  pending: "secondary",
  searched: "outline",
  failed: "destructive",
}

function verdictLabel(reason: string): string {
  return reason in VERDICT_LABELS
    ? VERDICT_LABELS[reason as keyof typeof VERDICT_LABELS]
    : reason
}

/** Languagarr queue tab: replacement searches waiting for or sent to Sonarr. */
export function Queue() {
  const { data: queue, isLoading } = useLanguagarrQueue()
  const status = useLanguagarrStatus().data
  const runNow = useRunLanguagarr()
  const clearPending = useClearLanguagarrPending()
  const sonarrUrl = useSonarrLinkBase()

  if (isLoading || !queue) {
    return <p className="text-sm text-muted-foreground">Loading queue…</p>
  }

  const settings = status?.settings
  const busy = runNow.isPending || clearPending.isPending
  return (
    <div className="flex flex-col gap-4">
      <section className="grid gap-3 md:grid-cols-3">
        <StatBlock label="Pending" value={queue.counts.pending} />
        <StatBlock label="Searched" value={queue.counts.searched} />
        <StatBlock label="Failed" value={queue.counts.failed} />
      </section>
      <p className="text-sm text-muted-foreground">
        {settings?.enabled
          ? `The worker sends up to ${settings.searches_per_run} search(es) every ${settings.interval_minutes} minutes.`
          : "The scheduled worker is off; pending searches wait until you enable it or run a batch now."}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          onClick={() => runNow.mutate()}
          disabled={busy || queue.counts.pending === 0}
        >
          <PlayIcon className="size-4" />
          Run a batch now
        </Button>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              type="button"
              variant="outline"
              disabled={busy || queue.counts.pending === 0}
            >
              <XCircleIcon className="size-4" />
              Clear pending
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Clear pending searches?</AlertDialogTitle>
              <AlertDialogDescription>
                Removes {queue.counts.pending} queued search(es). Files are not
                touched; you can queue them again after the next scan.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => clearPending.mutate()}>
                Clear pending
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
      {queue.rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">The queue is empty.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>File</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Queued</TableHead>
              <TableHead>Last attempt</TableHead>
              <TableHead>Attempts</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {queue.rows.map((row) => (
              <TableRow key={row.episode_file_id}>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{row.title}</span>
                    <SonarrSeriesLink
                      baseUrl={sonarrUrl}
                      slug={row.series_slug}
                      title={row.title}
                    />
                  </div>
                  {row.last_error ? (
                    <div className="text-xs text-destructive">
                      {row.last_error}
                    </div>
                  ) : null}
                </TableCell>
                <TableCell>{verdictLabel(row.reason)}</TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANTS[row.status]}>
                    {QUEUE_LABELS[row.status]}
                  </Badge>
                </TableCell>
                <TableCell>{formatTimestamp(row.queued_at)}</TableCell>
                <TableCell>
                  {row.searched_at ? formatTimestamp(row.searched_at) : "—"}
                </TableCell>
                <TableCell className="tabular-nums">{row.attempts}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
