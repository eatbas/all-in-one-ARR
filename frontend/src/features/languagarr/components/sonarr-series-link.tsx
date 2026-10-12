import { ExternalLinkIcon } from "lucide-react"

import { sonarrSeriesUrl } from "@/shared/lib/api"

interface SonarrSeriesLinkProps {
  /** Browser-facing Sonarr base URL; no link is rendered without one. */
  baseUrl: string | undefined
  /** Sonarr `titleSlug`; no link is rendered without one. */
  slug: string | null
  /** What the link opens, for its accessible name. */
  title: string
}

/** Opens a series' page in Sonarr in a new tab. */
export function SonarrSeriesLink({
  baseUrl,
  slug,
  title,
}: SonarrSeriesLinkProps) {
  if (!baseUrl || !slug) return null
  return (
    <a
      href={sonarrSeriesUrl(baseUrl, slug)}
      target="_blank"
      rel="noreferrer noopener"
      title={`Open ${title} in Sonarr`}
      aria-label={`Open ${title} in Sonarr`}
      className="inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
    >
      <ExternalLinkIcon className="size-3.5" />
      Sonarr
    </a>
  )
}
