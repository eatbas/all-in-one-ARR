import { LinkIcon } from "lucide-react"

import { Card, CardHeader, CardTitle } from "@/shared/components/ui/card"
import { PillLabel } from "@/shared/components/poster-pill/poster-pill"
import {
  pillIcon,
  pillIconSlot,
  pillShell,
} from "@/shared/components/poster-pill/poster-pill-variants"
import { cn } from "@/shared/lib/utils"
import type { ServiceStatus } from "@/shared/lib/api"

interface IntegrationStatusCardProps {
  label: string
  status: ServiceStatus | undefined
  /** URL to the service's web UI; when present a link pill is shown. */
  url?: string
}

/**
 * Single-line card showing the current health of one integration: the title
 * sits left and the status pill plus optional link pill sit right, both
 * revealing their labels leftwards so the pair stays anchored to the card's
 * edge. The status detail (connection identity, version, or failure reason)
 * is exposed as a native tooltip on the card rather than a visible line.
 */
export function IntegrationStatusCard({
  label,
  status,
  url,
}: IntegrationStatusCardProps) {
  const ok = status?.ok ?? false
  const detail = status?.detail ?? "Not checked yet"

  return (
    <Card className="py-0" title={detail}>
      <CardHeader className="flex flex-row items-center justify-between gap-2 px-3 py-1.5">
        <CardTitle className="truncate text-sm font-medium">{label}</CardTitle>
        <div className="flex shrink-0 items-center gap-1">
          <span
            className={cn(
              pillShell(6),
              "group/status bg-background/85 text-muted-foreground backdrop-blur-sm hover:z-10 hover:text-foreground",
            )}
            title={ok ? "Online" : "Offline"}
            aria-label={ok ? "Online" : "Offline"}
          >
            <PillLabel group="status" side="left" density={6}>
              {ok ? "Online" : "Offline"}
            </PillLabel>
            <span
              aria-hidden="true"
              className={pillIconSlot(6)}
              data-pill-icon-slot
            >
              <span
                className={cn(
                  "size-2.5 rounded-full",
                  ok ? "bg-emerald-500" : "bg-red-500",
                )}
              />
            </span>
          </span>
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noreferrer noopener"
              title={`Open ${label}`}
              aria-label={`Open ${label}`}
              className={cn(
                pillShell(6),
                "group/link bg-background/85 text-muted-foreground backdrop-blur-sm hover:z-10 hover:text-foreground focus-visible:z-10",
              )}
            >
              <PillLabel group="link" side="left" density={6}>
                {label}
              </PillLabel>
              <span
                aria-hidden="true"
                className={pillIconSlot(6)}
                data-pill-icon-slot
              >
                <LinkIcon className={pillIcon(6)} />
              </span>
            </a>
          ) : null}
        </div>
      </CardHeader>
    </Card>
  )
}
