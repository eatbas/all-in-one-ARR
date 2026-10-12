import { useState } from "react"
import { ChevronDownIcon, TvIcon } from "lucide-react"

import {
  ACTION_LABELS,
  isActionable,
  QUEUE_LABELS,
  VERDICT_LABELS,
  type SeriesGroup as SeriesGroupData,
} from "@/features/languagarr/review-groups"
import { Badge } from "@/shared/components/ui/badge"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table"

interface SeriesGroupProps {
  group: SeriesGroupData
  selected: ReadonlySet<number>
  onSelect: (episodeFileIds: number[], checked: boolean) => void
}

/** One collapsible series of non-compliant files with per-file selection. */
export function SeriesGroup({ group, selected, onSelect }: SeriesGroupProps) {
  const [isOpen, setIsOpen] = useState(true)
  const ids = group.items
    .filter(isActionable)
    .map((item) => item.episode_file_id)
  const selectedCount = ids.filter((id) => selected.has(id)).length
  const allSelected = ids.length > 0 && selectedCount === ids.length

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} asChild>
      <section
        className="rounded-lg border bg-background"
        aria-label={group.title}
      >
        <div className="flex items-center justify-between gap-3 border-b p-4">
          <label className="flex min-w-0 items-center gap-2">
            <input
              type="checkbox"
              className="size-4"
              checked={allSelected}
              ref={(element) => {
                if (element) {
                  element.indeterminate = selectedCount > 0 && !allSelected
                }
              }}
              onChange={(event) => onSelect(ids, event.target.checked)}
              disabled={ids.length === 0}
              aria-label={`Select all files in ${group.title}`}
            />
            <TvIcon className="size-4 shrink-0 text-muted-foreground" />
            <span className="truncate text-sm font-semibold">
              {group.title}
            </span>
            <Badge variant="secondary">{group.items.length} file(s)</Badge>
          </label>
          <CollapsibleTrigger
            className="rounded-md p-1 hover:bg-accent"
            aria-label={`${isOpen ? "Collapse" : "Expand"} ${group.title}`}
          >
            <ChevronDownIcon
              className={`size-4 transition-transform ${isOpen ? "" : "-rotate-90"}`}
            />
          </CollapsibleTrigger>
        </div>
        <CollapsibleContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10" />
                <TableHead>Episode</TableHead>
                <TableHead>Audio tracks</TableHead>
                <TableHead>Verdict</TableHead>
                <TableHead>Group</TableHead>
                <TableHead>Score / cutoff</TableHead>
                <TableHead>Fix</TableHead>
                <TableHead>Queue</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {group.items.map((item) => (
                <TableRow key={item.episode_file_id}>
                  <TableCell>
                    <input
                      type="checkbox"
                      className="size-4"
                      checked={selected.has(item.episode_file_id)}
                      onChange={(event) =>
                        onSelect([item.episode_file_id], event.target.checked)
                      }
                      disabled={!isActionable(item)}
                      aria-label={`Select ${group.title} ${item.episode_label}`}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="font-medium">{item.episode_label}</div>
                    <div
                      className="max-w-xs truncate font-mono text-xs text-muted-foreground"
                      title={item.relative_path}
                    >
                      {item.relative_path}
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {item.audio_languages}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">
                      {VERDICT_LABELS[item.verdict]}
                    </Badge>
                  </TableCell>
                  <TableCell>{item.release_group ?? "—"}</TableCell>
                  <TableCell className="tabular-nums">
                    {item.custom_format_score} / {item.cutoff_format_score}
                  </TableCell>
                  <TableCell>
                    {isActionable(item) ? (
                      <Badge
                        variant={
                          item.recommended_action === "delete_and_search"
                            ? "destructive"
                            : "secondary"
                        }
                      >
                        {ACTION_LABELS[item.recommended_action]}
                      </Badge>
                    ) : (
                      <Badge
                        variant="outline"
                        title="Every episode in this file is unmonitored, so Languagarr will not search or delete it."
                      >
                        Not searchable (unmonitored)
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>{QUEUE_LABELS[item.queue_status]}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CollapsibleContent>
      </section>
    </Collapsible>
  )
}
