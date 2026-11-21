import { useState } from "react"
import { ChevronDownIcon, TvIcon } from "lucide-react"

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
import type { RemindarrSeriesGroup } from "@/shared/lib/api"
import { formatCount } from "@/shared/lib/format"
import { cn } from "@/shared/lib/utils"

/** "20 Nov 2026" for an episode's UTC air date, or an em dash when unknown. */
function airDate(iso: string | null): string {
  if (iso === null) return "—"
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" })
}

interface SeriesReminderGroupProps {
  group: RemindarrSeriesGroup
  /** Start expanded (groups with a new-today episode, and the newest group). */
  defaultOpen: boolean
}

/**
 * One collapsible series with its unwatched episodes, newest aired first. A
 * series whose only details are episodes not in Plex yet has no unwatched
 * badge and explains that instead of showing an empty table.
 */
export function SeriesReminderGroup({
  group,
  defaultOpen,
}: SeriesReminderGroupProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  const title = group.series_title
  const hasUnwatched = group.episodes.length > 0

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} asChild>
      <section className="rounded-lg border bg-background" aria-label={title}>
        <div
          className={cn(
            "flex items-center justify-between gap-3 p-4",
            isOpen && "border-b",
          )}
        >
          <TvIcon
            aria-hidden="true"
            className="size-4 shrink-0 text-muted-foreground"
          />
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
            <span className="truncate text-sm font-semibold">{title}</span>
            {hasUnwatched ? (
              <Badge variant="secondary">
                {group.episodes.length} unwatched
              </Badge>
            ) : null}
            {group.episodes_not_in_plex > 0 ? (
              <span className="text-xs text-muted-foreground">
                {formatCount(group.episodes_not_in_plex, "episode")} not in Plex
                yet
              </span>
            ) : null}
          </div>
          <CollapsibleTrigger
            className="rounded-md p-1 hover:bg-accent"
            aria-label={`${isOpen ? "Collapse" : "Expand"} ${title}`}
          >
            <ChevronDownIcon
              className={cn(
                "size-4 transition-transform",
                !isOpen && "-rotate-90",
              )}
            />
          </CollapsibleTrigger>
        </div>
        <CollapsibleContent>
          {hasUnwatched ? (
            <EpisodeTable group={group} />
          ) : (
            <p className="p-4 text-sm text-muted-foreground">
              Every episode Plex lists has been watched. Plex does not list the
              rest yet, so their watch state is unknown.
            </p>
          )}
        </CollapsibleContent>
      </section>
    </Collapsible>
  )
}

/** The unwatched episodes of one series group. */
function EpisodeTable({ group }: { group: RemindarrSeriesGroup }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="pl-4">Episode</TableHead>
          <TableHead>Air date</TableHead>
          <TableHead>
            <span className="sr-only">Status</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {group.episodes.map((episode) => (
          <TableRow
            key={episode.episode_id}
            className={cn(episode.new_today && "bg-muted/60")}
          >
            <TableCell className="pl-4">
              <span className="font-medium">{episode.label}</span>
              {episode.title ? ` – ${episode.title}` : null}
            </TableCell>
            <TableCell className="tabular-nums">
              {airDate(episode.air_date_utc)}
            </TableCell>
            <TableCell>
              {episode.new_today ? <Badge>New today</Badge> : null}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
