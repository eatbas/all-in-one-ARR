import { cn } from "@/shared/lib/utils"

export type PillGroup = "link" | "status" | "add"
export type PillDensity = 5 | 6 | 7
export type PillLabelSide = "left" | "right"

const SIZE: Record<
  PillDensity,
  { shell: string; iconSlot: string; label: string; icon: string }
> = {
  5: { shell: "size-8", iconSlot: "size-8", label: "text-xs", icon: "size-4" },
  6: {
    shell: "size-7",
    iconSlot: "size-7",
    label: "text-[11px]",
    icon: "size-3.5",
  },
  7: {
    shell: "size-6",
    iconSlot: "size-6",
    label: "text-[10px]",
    icon: "size-3",
  },
}

/**
 * Shared container recipe. At rest every pill has a fixed square size and
 * therefore renders as a perfect circle; group-specific expansion classes let
 * the hovered or focused pill grow into a lozenge.
 */
export function pillShell(density: PillDensity): string {
  return cn(
    "inline-flex items-center justify-center overflow-hidden rounded-full shadow-sm transition-all outline-none motion-reduce:transition-none",
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

/** Width expansion for the shell itself while a label is revealed. */
export const PILL_EXPAND: Record<PillGroup, string> = {
  link: "hover:w-auto focus-visible:w-auto",
  status: "hover:w-auto",
  add: "hover:w-auto focus-visible:w-auto",
}

const REVEAL_WIDTH: Record<PillGroup, Record<PillDensity, string>> = {
  link: {
    5: "group-hover/link:max-w-20 group-focus-visible/link:max-w-20",
    6: "group-hover/link:max-w-16 group-focus-visible/link:max-w-16",
    7: "group-hover/link:max-w-14 group-focus-visible/link:max-w-14",
  },
  status: {
    5: "group-hover/status:max-w-24",
    6: "group-hover/status:max-w-20",
    7: "group-hover/status:max-w-20",
  },
  add: {
    5: "group-hover/add:max-w-10 group-focus-visible/add:max-w-10",
    6: "group-hover/add:max-w-9 group-focus-visible/add:max-w-9",
    7: "group-hover/add:max-w-8 group-focus-visible/add:max-w-8",
  },
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
  link: {
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
  },
  status: {
    5: { left: "group-hover/status:pl-2", right: "group-hover/status:pr-2" },
    6: {
      left: "group-hover/status:pl-1.5",
      right: "group-hover/status:pr-1.5",
    },
    7: {
      left: "group-hover/status:pl-1.5",
      right: "group-hover/status:pr-1.5",
    },
  },
  add: {
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
  },
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
