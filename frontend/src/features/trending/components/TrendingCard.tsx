import { useState } from "react"
import { CheckIcon, ExternalLinkIcon, FilmIcon } from "lucide-react"

import { Badge } from "@/shared/components/ui/badge"
import { posterUrl, trendingSourceUrl } from "@/shared/lib/api"
import type { TrendingItem } from "@/shared/lib/api"
import { cn } from "@/shared/lib/utils"
import { displayTitle, formatYear } from "@/shared/lib/format"
import { AddToListControl } from "@/features/trending/components/AddToListControl"
import { ImdbRatingBadge } from "@/features/trending/components/ImdbRatingBadge"
import { SOURCE_LABELS } from "@/features/trending/trending-tab"

/** Labels for the Seer library statuses worth surfacing on a card. */
const SEER_STATUS_LABELS: Record<number, string> = {
  2: "Requested",
  3: "Processing",
  4: "Partial",
  5: "Available",
}

/**
 * One trending result: poster with corner overlays — a link to the source's
 * dedicated page (top-right), the add-to-list control (bottom-right), and the
 * Tracked / In-library / Seer-status badges — plus the title and IMDb rating.
 */
export function TrendingCard({
  item,
  seerUrl,
}: {
  item: TrendingItem
  /** Configured Seer base URL, used to deep-link Seer-sourced items. */
  seerUrl?: string
}) {
  const [posterFailed, setPosterFailed] = useState(false)
  const label = displayTitle(item.title)
  const seerLabel =
    item.seer_status !== null ? SEER_STATUS_LABELS[item.seer_status] : undefined
  const sourceUrl = trendingSourceUrl(item, seerUrl)
  const sourceLabel = SOURCE_LABELS[item.source]

  return (
    <li className="flex flex-col gap-1">
      {/* A thick green ring marks titles already in Radarr (movies) / Sonarr
          (shows), so they stand out at a glance from new discoveries. */}
      <div
        className={cn(
          "relative rounded-md",
          item.in_library && "ring-[3px] ring-emerald-500",
        )}
      >
        {item.tmdb === null || posterFailed ? (
          <div
            role="img"
            aria-label={`No poster for ${label}`}
            className="flex aspect-[2/3] w-full items-center justify-center rounded-md bg-muted text-muted-foreground"
          >
            <FilmIcon className="size-8" />
          </div>
        ) : (
          <img
            src={posterUrl(item.media_type, item.tmdb)}
            alt={label}
            loading="lazy"
            onError={() => setPosterFailed(true)}
            className="aspect-[2/3] w-full rounded-md object-cover"
          />
        )}
        {item.already_tracked ? (
          <Badge
            variant="outline"
            className="absolute left-1 top-1 bg-background/85 shadow-sm backdrop-blur-sm"
          >
            Tracked
          </Badge>
        ) : null}
        {sourceUrl ? (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noreferrer noopener"
            title={`Open on ${sourceLabel}`}
            aria-label={`Open ${label} on ${sourceLabel}`}
            className="absolute right-1 top-1 inline-flex items-center justify-center rounded-md bg-background/85 p-1 text-muted-foreground shadow-sm backdrop-blur-sm transition-colors hover:text-foreground"
          >
            <ExternalLinkIcon className="size-4" />
          </a>
        ) : null}
        {/* Informational badges stack at the bottom-left, clear of the add control. */}
        <div className="absolute left-1 bottom-1 flex flex-col items-start gap-1">
          {item.in_library ? (
            <Badge
              aria-label="In library"
              className="gap-1 border-transparent bg-emerald-500 text-white shadow-sm"
            >
              <CheckIcon className="size-3" />
              In library
            </Badge>
          ) : null}
          {seerLabel ? (
            <Badge
              variant="outline"
              className="bg-background/85 shadow-sm backdrop-blur-sm"
            >
              {seerLabel}
            </Badge>
          ) : null}
        </div>
        <div className="absolute right-1 bottom-1">
          <AddToListControl item={item} />
        </div>
      </div>
      <span className="truncate text-xs font-medium" title={label}>
        {label}
      </span>
      {/* Year · type on the left, IMDb rating on the right of the same line. */}
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="truncate capitalize">
          {formatYear(item.year)} · {item.media_type}
        </span>
        <ImdbRatingBadge item={item} />
      </div>
    </li>
  )
}
