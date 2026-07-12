import type { LucideIcon } from "lucide-react"

import { cn } from "@/shared/lib/utils"
import { PillLabel } from "@/shared/components/poster-pill/poster-pill"
import {
  pillIcon,
  pillIconSlot,
  pillShell,
  type PillDensity,
} from "@/shared/components/poster-pill/poster-pill-variants"

/** Colour tones for the circular status pill, one per surfaced lifecycle state. */
export type StatusPillTone = "available" | "pending" | "synced" | "removed"

const STATUS_TONE_CLASSES: Record<StatusPillTone, string> = {
  available:
    "bg-background/85 text-emerald-600 ring-2 ring-inset ring-emerald-500 backdrop-blur-sm dark:text-emerald-500",
  pending:
    "bg-background/85 text-amber-600 ring-2 ring-inset ring-amber-500 backdrop-blur-sm dark:text-amber-500",
  synced:
    "bg-background/85 text-sky-600 ring-2 ring-inset ring-sky-500 backdrop-blur-sm dark:text-sky-500",
  removed:
    "bg-background/85 text-muted-foreground ring-2 ring-inset ring-muted-foreground/60 backdrop-blur-sm",
}

/**
 * Optical centring of each glyph inside the circular pill. Lucide's check stroke
 * spans y 6–17 of the 24-unit viewBox, so it sits high; a small downward shift
 * drops its visual mass onto the pill's centre line. The clock's outline is a
 * circle already concentric with the pill, so it takes no shift — nudging it
 * would push that inner circle off-centre from the surrounding ring. The synced
 * and removed glyphs are likewise symmetric within their viewBox and stay
 * unshifted.
 */
const STATUS_ICON_CLASSES: Record<StatusPillTone, string> = {
  available: "block translate-y-[4%]",
  pending: "block",
  synced: "block",
  removed: "block",
}

/**
 * Circular status pill shared by the poster grids: an icon-only circle at rest
 * that expands on hover to reveal a short label, while the full precise status
 * stays in `title` and `aria-label`.
 */
export function StatusPill({
  detail,
  label,
  density,
  tone,
  Icon,
}: {
  /** Full precise status, exposed via `title` and `aria-label`. */
  detail: string
  /** Short label revealed while the pill is hovered. */
  label: string
  /** Posters-per-row density; controls pill and icon size. */
  density: PillDensity
  /** Colour treatment for the pill's ring, icon, and revealed text. */
  tone: StatusPillTone
  /** Lucide glyph rendered in the pill's fixed icon slot. */
  Icon: LucideIcon
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
