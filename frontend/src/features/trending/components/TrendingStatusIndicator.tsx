import { CheckIcon, ClockIcon } from "lucide-react"

import type { TrendingItem } from "@/shared/lib/api"
import { cn } from "@/shared/lib/utils"
import {
  isAvailable,
  isPending,
} from "@/features/trending/trending-item-status"
import { PillLabel } from "@/features/trending/components/poster-pill"
import {
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

/** Visible pill words: the full word, or a prefix once the poster is dense. */
const AVAILABLE_LABEL = { full: "Available", short: "Ava." }
const PENDING_LABEL = { full: "Pending", short: "Pend." }
/**
 * Density at/above which the status label switches to its prefix form, so the
 * expanded lozenge does not exceed roughly 60% of the (now narrow) poster width.
 */
const ABBREVIATE_AT_DENSITY: PillDensity = 9

/** Pick the full word or its prefix for the given density. */
function statusLabel(
  text: { full: string; short: string },
  density: PillDensity,
): string {
  return density >= ABBREVIATE_AT_DENSITY ? text.short : text.full
}

type StatusIcon = typeof CheckIcon

type StatusPillTone = "available" | "pending"

const STATUS_TONE_CLASSES: Record<StatusPillTone, string> = {
  available:
    "bg-background/85 text-emerald-600 ring-2 ring-inset ring-emerald-500 backdrop-blur-sm dark:text-emerald-500",
  pending:
    "bg-background/85 text-amber-600 ring-2 ring-inset ring-amber-500 backdrop-blur-sm dark:text-amber-500",
}

/**
 * Optical centring of each glyph inside the circular pill. Lucide's check stroke
 * spans y 6–17 of the 24-unit viewBox, so it sits high; a small downward shift
 * drops its visual mass onto the pill's centre line. The clock's outline is a
 * circle already concentric with the pill, so it takes no shift — nudging it
 * would push that inner circle off-centre from the surrounding ring.
 */
const STATUS_ICON_CLASSES: Record<StatusPillTone, string> = {
  available: "block translate-y-[4%]",
  pending: "block",
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
        "group/status hover:z-10",
        STATUS_TONE_CLASSES[tone],
      )}
    >
      <span
        aria-hidden="true"
        className={pillIconSlot(density)}
        data-pill-icon-slot
      >
        <Icon className={cn(pillIcon(density), STATUS_ICON_CLASSES[tone])} />
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
    return (
      <StatusPill
        detail="Available"
        label={statusLabel(AVAILABLE_LABEL, density)}
        density={density}
        tone="available"
        Icon={CheckIcon}
      />
    )
  }
  if (isPending(item)) {
    return (
      <StatusPill
        detail={pendingLabel(item)}
        label={statusLabel(PENDING_LABEL, density)}
        density={density}
        tone="pending"
        Icon={ClockIcon}
      />
    )
  }
  return null
}
