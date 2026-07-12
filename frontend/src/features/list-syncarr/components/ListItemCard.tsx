import { LinkIcon, Trash2Icon } from "lucide-react"

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
import { PillLabel } from "@/shared/components/poster-pill/poster-pill"
import {
  pillIcon,
  pillIconSlot,
  pillShell,
} from "@/shared/components/poster-pill/poster-pill-variants"
import type { PosterDensity } from "@/shared/components/poster-grid/poster-grid-density"
import { ItemStatusPill } from "@/features/list-syncarr/components/item-status-pill"
import { PosterThumb } from "@/features/list-syncarr/components/poster-thumb"
import { cn } from "@/shared/lib/utils"
import { displayTitle, formatYear } from "@/shared/lib/format"
import { seerMediaUrl } from "@/shared/lib/api"
import type { Item } from "@/shared/lib/api"

interface ListItemCardProps {
  item: Item
  /** Seer base URL, when configured, used to deep-link each item's request page. */
  seerUrl?: string
  /** Posters-per-row density for the grid and every overlay pill. */
  density: PosterDensity
  /** Remove a single item from its Trakt list (already user-confirmed). */
  onDelete: (item: Item) => void
}

/** One poster card with delete/Seer/status overlays and a caption. */
export function ListItemCard({
  item,
  seerUrl,
  density,
  onDelete,
}: ListItemCardProps) {
  const title = displayTitle(item.title)
  const seerLink =
    seerUrl && item.tmdb !== null
      ? seerMediaUrl(seerUrl, item.type, item.tmdb)
      : undefined

  return (
    <li className="flex flex-col gap-1">
      {/* Poster overlays: a per-item delete control top-left, the
        Seer request link top-right, the status pill bottom-left. */}
      <div className="relative">
        <PosterThumb item={item} />
        {/* Already-removed items are no longer on the Trakt list, so they
          offer no delete control. */}
        {item.status !== "removed" ? (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <button
                type="button"
                title={`Remove "${title}" from the list`}
                aria-label={`Remove "${title}" from the list`}
                className={cn(
                  pillShell(density),
                  // pillShell strips the browser outline, so the
                  // pill supplies its own focus-visible ring on top
                  // of the label reveal.
                  "group/delete absolute left-1 top-1 bg-background/85 text-muted-foreground backdrop-blur-sm hover:z-10 hover:text-destructive focus-visible:z-10 focus-visible:ring-[3px] focus-visible:ring-ring/50",
                )}
              >
                <span
                  aria-hidden="true"
                  className={pillIconSlot(density)}
                  data-pill-icon-slot
                >
                  <Trash2Icon className={pillIcon(density)} />
                </span>
                <PillLabel group="delete" side="right" density={density}>
                  Remove
                </PillLabel>
              </button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Remove "{title}"?</AlertDialogTitle>
                <AlertDialogDescription>
                  It will be removed from its Trakt list.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={() => onDelete(item)}>
                  Remove
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        ) : null}
        {seerLink ? (
          <a
            href={seerLink}
            target="_blank"
            rel="noreferrer noopener"
            title={`Request "${title}" in Seer`}
            aria-label={`Request "${title}" in Seer`}
            className={cn(
              pillShell(density),
              "group/link absolute right-1 top-1 bg-background/85 text-muted-foreground backdrop-blur-sm hover:z-10 hover:text-foreground focus-visible:z-10",
            )}
          >
            <PillLabel group="link" side="left" density={density}>
              Seer
            </PillLabel>
            <span
              aria-hidden="true"
              className={pillIconSlot(density)}
              data-pill-icon-slot
            >
              <LinkIcon className={pillIcon(density)} />
            </span>
          </a>
        ) : null}
        {/* The status pill sits bottom-left, mirroring Trending. */}
        <div className="absolute left-1 bottom-1">
          <ItemStatusPill status={item.status} density={density} />
        </div>
      </div>
      <span className="truncate text-xs font-medium" title={title}>
        {title}
      </span>
      {/* Year and media type on one row beneath the poster. */}
      <span className="truncate text-xs capitalize text-muted-foreground">
        {formatYear(item.year)} · {item.type}
      </span>
    </li>
  )
}
