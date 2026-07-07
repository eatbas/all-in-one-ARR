import { CheckIcon, ClockIcon } from "lucide-react"

import type { TrendingItem } from "@/shared/lib/api"
import { cn } from "@/shared/lib/utils"
import {
  isAvailable,
  isPending,
} from "@/features/trending/trending-item-status"
import { PillLabel } from "@/features/trending/components/poster-pill"
import {
  PILL_EXPAND,
  pillIcon,
  pillIconSlot,
  pillShell,
  type PillDensity,
} from "@/features/trending/components/poster-pill-variants"

/** Labels for the Seer library statuses worth surfacing on a card. */
const SEER_STATUS_LABELS: Record<number, string> = {
  2: "Requested",
  3: "Processing",
  4: "Partial",
  5: "Available",
}

/** The most specific human label for an in-progress item, preferring Seer detail. */
function pendingLabel(item: TrendingItem): string {
  const seerLabel =
    item.seer_status !== null ? SEER_STATUS_LABELS[item.seer_status] : undefined
  return seerLabel ?? "In library, media not downloaded"
}

/**
 * Concise visible label for the pending pill. Falls back to "In progress" so
 * the expanded lozenge stays short and never overruns the card centre.
 */
function shortPendingLabel(item: TrendingItem): string {
  const seerLabel =
    item.seer_status !== null ? SEER_STATUS_LABELS[item.seer_status] : undefined
  return seerLabel ?? "In progress"
}

type StatusIcon = typeof CheckIcon

type StatusPillTone = "available" | "pending"

const STATUS_TONE_CLASSES: Record<StatusPillTone, string> = {
  available: "bg-emerald-500 text-white",
  pending:
    "bg-background/85 text-amber-600 ring-2 ring-inset ring-amber-500 backdrop-blur-sm dark:text-amber-500",
}

function StatusPill({
  detail,
  label,
  density,
  tone,
  Icon,
}: {
  detail: string
  label: string
  density: PillDensity
  tone: StatusPillTone
  Icon: StatusIcon
}) {
  return (
    <span
      role="img"
      aria-label={detail}
      title={detail}
      className={cn(
        pillShell(density),
        PILL_EXPAND.status,
        "group/status hover:z-10",
        STATUS_TONE_CLASSES[tone],
      )}
    >
      <span
        aria-hidden="true"
        className={pillIconSlot(density)}
        data-pill-icon-slot
      >
        <Icon className={pillIcon(density)} />
      </span>
      <PillLabel group="status" side="right" density={density}>
        {label}
      </PillLabel>
    </span>
  )
}

/**
 * Compact availability marker for a trending card: a solid green pill with a
 * tick when the title is watchable now, an amber clock pill while it is on its
 * way (requested / processing / partial / downloading). The full precise status
 * stays in `title` and `aria-label`; the pill expands on hover to show a short
 * visible label. Renders nothing for items with no library or Seer state worth
 * showing.
 */
export function TrendingStatusIndicator({
  item,
  density = 5,
}: {
  item: TrendingItem
  /** Posters-per-row density; controls pill and icon size. Defaults to the
   *  largest size for consumers that do not know the grid density. */
  density?: PillDensity
}) {
  if (isAvailable(item)) {
    const detail = item.in_library_available ? "In library" : "Available"
    return (
      <StatusPill
        detail={detail}
        label={detail}
        density={density}
        tone="available"
        Icon={CheckIcon}
      />
    )
  }
  if (isPending(item)) {
    const detail = pendingLabel(item)
    return (
      <StatusPill
        detail={detail}
        label={shortPendingLabel(item)}
        density={density}
        tone="pending"
        Icon={ClockIcon}
      />
    )
  }
  return null
}
