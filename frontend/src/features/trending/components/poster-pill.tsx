import { cn } from "@/shared/lib/utils"
import {
  type PillDensity,
  type PillGroup,
  type PillLabelSide,
  pillLabelReveal,
  pillLabelText,
} from "@/features/trending/components/poster-pill-variants"

/**
 * Collapsed label span that expands on its pill's hover/focus. The outer-edge
 * padding is applied only while expanded (via the per-group `REVEAL` classes)
 * so the collapsed span has zero width and every pill stays a perfect circle
 * at rest, while the revealed word sits clear of the pill's rounded cap.
 */
export function PillLabel({
  group,
  side,
  density,
  children,
}: {
  /** Which `group/<name>` this label belongs to; selects the reveal classes. */
  group: PillGroup
  /** Side of the icon that the label appears on when expanded. */
  side: PillLabelSide
  /** Posters-per-row density; controls label text size. */
  density: PillDensity
  children: React.ReactNode
}) {
  return (
    <span
      className={cn(
        "max-w-0 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap opacity-0 transition-all duration-200 motion-reduce:transition-none",
        pillLabelText(density),
        pillLabelReveal(group, density, side),
      )}
    >
      {children}
    </span>
  )
}
