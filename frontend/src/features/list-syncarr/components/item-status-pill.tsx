import { CheckIcon, ClockIcon, RefreshCwIcon, XIcon } from "lucide-react"
import type { LucideIcon } from "lucide-react"

import {
  StatusPill,
  type StatusPillTone,
} from "@/shared/components/poster-pill/status-pill"
import type { PillDensity } from "@/shared/components/poster-pill/poster-pill-variants"
import type { ItemStatus } from "@/shared/lib/api"

/**
 * Pill treatment per item lifecycle status. `requested` reveals "Pending" to
 * match how the Trending cards present an in-flight Seer request; the precise
 * word stays in the pill's `title`/`aria-label` via `detail`.
 */
const STATUS_PILLS: Record<
  ItemStatus,
  { tone: StatusPillTone; Icon: LucideIcon; label: string; detail: string }
> = {
  available: {
    tone: "available",
    Icon: CheckIcon,
    label: "Available",
    detail: "Available",
  },
  requested: {
    tone: "pending",
    Icon: ClockIcon,
    label: "Pending",
    detail: "Requested",
  },
  synced: {
    tone: "synced",
    Icon: RefreshCwIcon,
    label: "Synced",
    detail: "Synced from Trakt",
  },
  removed: {
    tone: "removed",
    Icon: XIcon,
    label: "Removed",
    detail: "Removed from the list",
  },
}

/**
 * Circular status pill for a mirrored item's poster, using the same shared
 * pill chassis as the Trending cards so both grids speak one visual language.
 */
export function ItemStatusPill({
  status,
  density,
}: {
  status: ItemStatus
  /** Posters-per-row density; controls pill and icon size. */
  density: PillDensity
}) {
  const pill = STATUS_PILLS[status]
  return (
    <StatusPill
      detail={pill.detail}
      label={pill.label}
      density={density}
      tone={pill.tone}
      Icon={pill.Icon}
    />
  )
}
