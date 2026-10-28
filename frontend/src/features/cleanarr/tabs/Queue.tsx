import { EyeOffIcon, FlaskConicalIcon } from "lucide-react"

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
import {
  PILL_BASE,
  PILL_STYLES,
  REASON_META,
  sourceLabel,
} from "@/features/cleanarr/labels"
import type { CleanarrQueueItem } from "@/shared/lib/api"
import {
  useCleanarrQueue,
  useCleanarrStatus,
  useIgnoreCleanarrDownload,
} from "@/shared/lib/queries"
import { cn } from "@/shared/lib/utils"

/** "Next run" cell: what the next run does with this item. */
function NextRun({
  item,
  dryRun,
}: {
  item: CleanarrQueueItem
  dryRun: boolean
}) {
  if (item.ignored) return <Badge variant="secondary">Ignored</Badge>
  if (item.excluded) {
    return (
      <span className="text-xs text-muted-foreground">Excluded by pattern</span>
    )
  }
  if (!item.would_remove)
    return <span className="text-muted-foreground">—</span>
  return dryRun ? (
    <Badge
      variant="outline"
      className="border-amber-500/40 text-amber-600 dark:text-amber-400"
    >
      <FlaskConicalIcon aria-hidden="true" />
      Would remove
    </Badge>
  ) : (
    <Badge
      variant="outline"
      className="border-red-500/40 text-red-600 dark:text-red-400"
    >
      Will remove next run
    </Badge>
  )
}

/** Cleanarr Queue tab: stuck usenet items with their strikes. */
export function Queue() {
  const { data: queue, isLoading, isError, error } = useCleanarrQueue()
  const settings = useCleanarrStatus().data?.settings
  const ignore = useIgnoreCleanarrDownload()

  if (isError) {
    return (
      <p className="text-sm text-destructive">
        Could not load the queue: {error.message}
      </p>
    )
  }
  if (isLoading || !queue) {
    return <p className="text-sm text-muted-foreground">Loading queue…</p>
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Usenet items stuck in a failed import or failed download. An item is
        removed and blocklisted after {queue.max_strikes} strikes
        {settings
          ? ` (one per run, every ${settings.interval_minutes} minutes); up to ${settings.max_removals_per_run} removals per run.`
          : "."}
      </p>
      {Object.entries(queue.errors).map(([app, message]) => (
        <p key={app} className="text-sm text-destructive">
          {sourceLabel(app)}: queue unavailable. {message}
        </p>
      ))}
      {Object.entries(queue.held).map(([app, message]) => (
        <p key={app} className="text-sm text-amber-600 dark:text-amber-400">
          {sourceLabel(app)} — {message}
        </p>
      ))}
      {queue.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No stuck or failed downloads in the queue.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>App</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Message</TableHead>
              <TableHead>Strikes</TableHead>
              <TableHead>Next run</TableHead>
              <TableHead>
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {queue.items.map((item) => {
              const reason = REASON_META[item.reason]
              return (
                <TableRow key={`${item.app}-${item.download_id}`}>
                  <TableCell>
                    <span
                      className="block max-w-[40ch] truncate font-medium"
                      title={item.title}
                    >
                      {item.title}
                    </span>
                  </TableCell>
                  <TableCell>{sourceLabel(item.app)}</TableCell>
                  <TableCell>
                    <span className={cn(PILL_BASE, PILL_STYLES[reason.tone])}>
                      {reason.label}
                    </span>
                  </TableCell>
                  <TableCell className="max-w-[32ch] whitespace-normal wrap-anywhere text-sm text-muted-foreground">
                    {item.message || "—"}
                  </TableCell>
                  <TableCell
                    className={cn(
                      "tabular-nums",
                      item.would_remove && "font-medium",
                      (item.ignored || item.strikes === 0) &&
                        "text-muted-foreground",
                    )}
                  >
                    {item.ignored
                      ? "—"
                      : `${item.strikes} / ${item.max_strikes}`}
                  </TableCell>
                  <TableCell>
                    <NextRun item={item} dryRun={queue.dry_run} />
                  </TableCell>
                  <TableCell>
                    {item.ignored ? null : (
                      <Button
                        size="xs"
                        variant="outline"
                        disabled={ignore.isPending}
                        onClick={() =>
                          ignore.mutate({
                            downloadId: item.download_id,
                            title: item.title,
                          })
                        }
                      >
                        <EyeOffIcon className="size-3" />
                        Ignore
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
