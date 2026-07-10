import { cn } from "@/shared/lib/utils"

export type PillGroup = "link" | "status" | "add"
export type PillDensity = 5 | 6 | 7 | 8 | 9 | 10 | 11
export type PillLabelSide = "left" | "right"

const SIZE: Record<
  PillDensity,
  { shell: string; iconSlot: string; label: string; icon: string }
> = {
  // Label fonts are one step smaller than the pills they sit in, so the revealed
  // word stays compact against the poster.
  // `shell` fixes only the height; the width hugs the content (see pillShell), so
  // the icon slot keeps the square `size-*` that renders the resting circle.
  5: {
    shell: "h-8",
    iconSlot: "size-8",
    label: "text-[11px]",
    icon: "size-4",
  },
  6: {
    shell: "h-7",
    iconSlot: "size-7",
    label: "text-[10px]",
    icon: "size-3.5",
  },
  7: {
    shell: "h-6",
    iconSlot: "size-6",
    label: "text-[9px]",
    icon: "size-3",
  },
  // Dense grids (8–11) keep shrinking so the overlay pills track the smaller
  // posters instead of clamping at the density-7 size.
  8: {
    shell: "h-[22px]",
    iconSlot: "size-[22px]",
    label: "text-[9px]",
    icon: "size-3",
  },
  9: {
    shell: "h-5",
    iconSlot: "size-5",
    label: "text-[8px]",
    icon: "size-[11px]",
  },
  10: {
    shell: "h-[18px]",
    iconSlot: "size-[18px]",
    label: "text-[8px]",
    icon: "size-2.5",
  },
  11: {
    shell: "h-4",
    iconSlot: "size-4",
    label: "text-[8px]",
    icon: "size-2",
  },
}

/**
 * Shared container recipe. The height is fixed per density while the width hugs
 * the content (`w-fit`): at rest the label is collapsed to zero width, so the
 * pill is a perfect circle; on hover it grows into a lozenge as the label
 * reveals. The width is deliberately content-driven rather than animated — only
 * colours transition here, and the smooth expand/collapse comes entirely from
 * the label's own `max-width` transition. Transitioning the shell width instead
 * would leave `justify-center` briefly re-centring the icon mid-animation, so
 * the glyph would visibly jitter each time the pointer enters or leaves.
 */
export function pillShell(density: PillDensity): string {
  return cn(
    "inline-flex w-fit items-center justify-center overflow-hidden rounded-full shadow-sm transition-colors outline-none motion-reduce:transition-none",
    SIZE[density].shell,
  )
}

/** Fixed slot that centres an icon identically in every pill. */
export function pillIconSlot(density: PillDensity): string {
  return cn("inline-grid shrink-0 place-items-center", SIZE[density].iconSlot)
}

/** Tailwind classes for an icon inside a pill of the given density. */
export function pillIcon(density: PillDensity): string {
  return SIZE[density].icon
}

/** Tailwind classes for the expanded label text of the given density. */
export function pillLabelText(density: PillDensity): string {
  return SIZE[density].label
}

/**
 * Extend a 5/6/7 density map to the full 5–11 range: the dense grids (8–11)
 * reuse the density-7 hover-reveal treatment. Only the resting pill size shrinks
 * further (via {@link SIZE}); the expanded lozenge needs no extra tuning because
 * the smaller-font labels fit within the same caps. Keeping one literal per
 * value also keeps the Tailwind class list free of duplicates.
 */
function withDenseFallback<T>(
  base: Record<5 | 6 | 7, T>,
): Record<PillDensity, T> {
  return { ...base, 8: base[7], 9: base[7], 10: base[7], 11: base[7] }
}

const REVEAL_WIDTH: Record<PillGroup, Record<PillDensity, string>> = {
  link: withDenseFallback({
    5: "group-hover/link:max-w-20 group-focus-visible/link:max-w-20",
    6: "group-hover/link:max-w-16 group-focus-visible/link:max-w-16",
    7: "group-hover/link:max-w-14 group-focus-visible/link:max-w-14",
  }),
  status: withDenseFallback({
    5: "group-hover/status:max-w-24",
    6: "group-hover/status:max-w-20",
    7: "group-hover/status:max-w-20",
  }),
  add: withDenseFallback({
    5: "group-hover/add:max-w-10 group-focus-visible/add:max-w-10",
    6: "group-hover/add:max-w-9 group-focus-visible/add:max-w-9",
    7: "group-hover/add:max-w-8 group-focus-visible/add:max-w-8",
  }),
}

const REVEAL_OPACITY: Record<PillGroup, string> = {
  link: "group-hover/link:opacity-100 group-focus-visible/link:opacity-100",
  status: "group-hover/status:opacity-100",
  add: "group-hover/add:opacity-100 group-focus-visible/add:opacity-100",
}

/**
 * Outer-edge padding for the revealed label, sized per density to mirror the
 * icon slot's built-in inset (8px at density 5, 7px at 6, 6px at 7). The slot
 * inset already separates the icon glyph from the word, so matching padding
 * on the far side keeps the word optically centred in the expanded lozenge
 * instead of touching the rounded cap and being clipped by it.
 */
const REVEAL_PADDING: Record<
  PillGroup,
  Record<PillDensity, Record<PillLabelSide, string>>
> = {
  link: withDenseFallback({
    5: {
      left: "group-hover/link:pl-2 group-focus-visible/link:pl-2",
      right: "group-hover/link:pr-2 group-focus-visible/link:pr-2",
    },
    6: {
      left: "group-hover/link:pl-1.5 group-focus-visible/link:pl-1.5",
      right: "group-hover/link:pr-1.5 group-focus-visible/link:pr-1.5",
    },
    7: {
      left: "group-hover/link:pl-1.5 group-focus-visible/link:pl-1.5",
      right: "group-hover/link:pr-1.5 group-focus-visible/link:pr-1.5",
    },
  }),
  status: withDenseFallback({
    5: { left: "group-hover/status:pl-2", right: "group-hover/status:pr-2" },
    6: {
      left: "group-hover/status:pl-1.5",
      right: "group-hover/status:pr-1.5",
    },
    7: {
      left: "group-hover/status:pl-1.5",
      right: "group-hover/status:pr-1.5",
    },
  }),
  add: withDenseFallback({
    5: {
      left: "group-hover/add:pl-2 group-focus-visible/add:pl-2",
      right: "group-hover/add:pr-2 group-focus-visible/add:pr-2",
    },
    6: {
      left: "group-hover/add:pl-1.5 group-focus-visible/add:pl-1.5",
      right: "group-hover/add:pr-1.5 group-focus-visible/add:pr-1.5",
    },
    7: {
      left: "group-hover/add:pl-1.5 group-focus-visible/add:pl-1.5",
      right: "group-hover/add:pr-1.5 group-focus-visible/add:pr-1.5",
    },
  }),
}

/**
 * Tailwind classes that reveal a collapsed label for each named pill group.
 * The padding is applied only while expanded — on the label's outer edge, away
 * from the icon — so the collapsed span has zero width and every pill stays a
 * perfect circle at rest, while the revealed word sits centred between the
 * icon and the pill's rounded cap.
 */
export function pillLabelReveal(
  group: PillGroup,
  density: PillDensity,
  side: PillLabelSide,
): string {
  return cn(
    REVEAL_WIDTH[group][density],
    REVEAL_OPACITY[group],
    REVEAL_PADDING[group][density][side],
  )
}
