import { useState } from "react"
import { FilmIcon } from "lucide-react"

import { posterUrl } from "@/shared/lib/api"
import type { Item } from "@/shared/lib/api"
import { displayTitle } from "@/shared/lib/format"

/**
 * Poster thumbnail for a mirrored item. Falls back to a film-icon placeholder
 * when the item has no TMDB id (so no poster can be resolved) or when the cached
 * poster request fails. The image is lazily loaded and the browser caches it via
 * the backend's `Cache-Control` header.
 */
export function PosterThumb({ item }: { item: Item }) {
  const [failed, setFailed] = useState(false)
  const label = displayTitle(item.title)

  if (item.tmdb === null || failed) {
    return (
      <div
        role="img"
        aria-label={`No poster for ${label}`}
        className="flex aspect-[2/3] w-full items-center justify-center rounded-md bg-muted text-muted-foreground"
      >
        <FilmIcon className="size-8" />
      </div>
    )
  }

  return (
    <img
      src={posterUrl(item.type, item.tmdb)}
      alt={label}
      loading="lazy"
      onError={() => setFailed(true)}
      className="aspect-[2/3] w-full rounded-md object-cover"
    />
  )
}
