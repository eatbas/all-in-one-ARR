import { useState } from "react"
import { FilmIcon, LinkIcon } from "lucide-react"

import { posterUrl, trendingSourceUrl } from "@/shared/lib/api"
import type { TrendingItem } from "@/shared/lib/api"
import { cn } from "@/shared/lib/utils"
import { displayTitle, formatYear } from "@/shared/lib/format"
import { AddToListControl } from "@/features/trending/components/AddToListControl"
import { ImdbRatingBadge } from "@/features/trending/components/ImdbRatingBadge"
import { PillLabel } from "@/features/trending/components/poster-pill"
import {
  pillIcon,
  pillIconSlot,
  pillShell,
  type PillDensity,
} from "@/features/trending/components/poster-pill-variants"
import { TrendingStatusIndicator } from "@/features/trending/components/TrendingStatusIndicator"
import {
  isAvailable,
  isPending,
} from "@/features/trending/trending-item-status"
import { SOURCE_LABELS } from "@/features/trending/trending-tab"

/**
 * One trending result: poster with corner overlays — a link to the source's
 * dedicated page (top-right), the add-to-list control (bottom-right), and the
 * availability indicator (bottom-left) — plus a hover overlay with the full
 * title and year, and the static title and media details beneath.
 */
export function TrendingCard({
  item,
  seerUrl,
  density = 5,
}: {
  item: TrendingItem
  /** Configured Seer base URL, used to deep-link Seer-sourced items. */
  seerUrl?: string
  /** Posters-per-row density; controls pill and icon size. Defaults to the
   *  largest size for consumers that do not know the grid density. */
  density?: PillDensity
}) {
  const [posterFailed, setPosterFailed] = useState(false)
  const label = displayTitle(item.title)
  const sourceUrl = trendingSourceUrl(item, seerUrl)
  const sourceLabel = SOURCE_LABELS[item.source]
  // Green = available to watch now (downloaded or Seer-Available); amber = on its way
  // (library record without the file yet, or requested/processing/partial).
  const available = isAvailable(item)
  const pending = isPending(item)

  return (
    <li className="flex flex-col gap-1">
      {/* A thick ring marks library/availability state at a glance: green when the
          title is available now, amber when it is still on its way. */}
      <div
        className={cn(
          "group/poster relative rounded-md",
          available && "ring-[3px] ring-emerald-500",
          !available && pending && "ring-[3px] ring-amber-500",
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
            src={posterUrl(item.media_type, item.tmdb, item.imdb)}
            alt={label}
            loading="lazy"
            onError={() => setPosterFailed(true)}
            className="aspect-[2/3] w-full rounded-md object-cover"
          />
        )}
        {/* Hover overlay: the full (untruncated) title and year, revealed on
            hover or keyboard focus within. It duplicates content that already
            exists in the static lines below, so it is hidden from assistive
            technology; pointer-events-none keeps the corner controls usable. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 bottom-0 rounded-b-md bg-linear-to-t from-black/80 via-black/50 to-transparent px-2 pt-6 pb-9 opacity-0 transition-opacity duration-200 group-hover/poster:opacity-100 group-focus-within/poster:opacity-100 motion-reduce:transition-none"
        >
          <p className="line-clamp-3 text-xs font-semibold text-white">
            {label}
          </p>
          <p className="text-[11px] text-white/80">{formatYear(item.year)}</p>
        </div>
        {sourceUrl ? (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noreferrer noopener"
            title={`Open on ${sourceLabel}`}
            aria-label={`Open ${label} on ${sourceLabel}`}
            className={cn(
              pillShell(density),
              "group/link absolute right-1 top-1 bg-background/85 text-muted-foreground backdrop-blur-sm hover:z-10 hover:text-foreground focus-visible:z-10",
            )}
          >
            <PillLabel group="link" side="left" density={density}>
              {sourceLabel}
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
        {/* IMDb star and rating sit in the poster's top-left corner. */}
        <div className="absolute left-1 top-1">
          <ImdbRatingBadge item={item} density={density} />
        </div>
        {/* The availability indicator sits bottom-left, clear of the add control. */}
        <div className="absolute left-1 bottom-1">
          <TrendingStatusIndicator item={item} density={density} />
        </div>
        <div className="absolute right-1 bottom-1">
          <AddToListControl item={item} density={density} />
        </div>
      </div>
      <span className="truncate text-xs font-medium" title={label}>
        {label}
      </span>
      {/* Year · media type beneath the poster. */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="truncate capitalize">
          {formatYear(item.year)} · {item.media_type}
        </span>
      </div>
    </li>
  )
}
