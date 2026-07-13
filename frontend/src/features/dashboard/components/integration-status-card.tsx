import { LinkIcon } from "lucide-react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { PillLabel } from "@/shared/components/poster-pill/poster-pill"
import {
  pillIcon,
  pillIconSlot,
  pillShell,
} from "@/shared/components/poster-pill/poster-pill-variants"
import { cn } from "@/shared/lib/utils"
import type { ServiceStatus } from "@/shared/lib/api"

interface IntegrationStatusCardProps {
  name: string
  label: string
  status: ServiceStatus | undefined
  /** URL to the service's web UI; when present a link pill is shown. */
  url?: string
  compact?: boolean
}

/** Small card showing the current health of a single integration. */
export function IntegrationStatusCard({
  label,
  status,
  url,
  compact = false,
}: IntegrationStatusCardProps) {
  const ok = status?.ok ?? false
  const detail = status?.detail ?? "Not checked yet"

  return (
    <Card className={cn("flex flex-col", compact && "gap-1 py-0")}>
      <CardHeader
        className={cn(
          "flex flex-row items-start justify-between gap-2 space-y-0",
          compact ? "px-3 py-2 pb-1" : "pb-2",
        )}
      >
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
        <div className="flex flex-col items-end">
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
      <CardContent className={cn("flex-1", compact && "px-3 py-1 pt-0")}>
        <div className="flex items-center justify-between gap-2">
          <CardDescription className="text-xs line-clamp-1">
            {detail}
          </CardDescription>
          <span
            className={cn(
              pillShell(6),
              "group/status shrink-0 bg-background/85 text-muted-foreground backdrop-blur-sm hover:z-10 hover:text-foreground",
            )}
            title={ok ? "Online" : "Offline"}
            aria-label={ok ? "Online" : "Offline"}
          >
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
            <span
              className={cn(
                "max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[10px] leading-none opacity-0 transition-all duration-200 group-hover/status:max-w-[5rem] group-hover/status:pr-[9px] group-hover/status:opacity-100 motion-reduce:transition-none",
              )}
            >
              {ok ? "Online" : "Offline"}
            </span>
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
