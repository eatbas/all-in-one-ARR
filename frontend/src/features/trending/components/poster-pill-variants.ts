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
  7: { shell: "size-6", iconSlot: "size-6", label: "text-[10px]", icon: "size-3" },
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
    7: "group-hover/status:max-w-16",
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

const REVEAL_PADDING: Record<PillGroup, Record<PillLabelSide, string>> = {
  link: {
    left: "group-hover/link:pr-1 group-focus-visible/link:pr-1",
    right: "group-hover/link:pl-1 group-focus-visible/link:pl-1",
  },
  status: {
    left: "group-hover/status:pr-1",
    right: "group-hover/status:pl-1",
  },
  add: {
    left: "group-hover/add:pr-1 group-focus-visible/add:pr-1",
    right: "group-hover/add:pl-1 group-focus-visible/add:pl-1",
  },
}

/**
 * Tailwind classes that reveal a collapsed label for each named pill group.
 * The label padding is applied only while expanded so the collapsed span has
 * zero width and every pill stays a perfect circle at rest.
 */
export function pillLabelReveal(
  group: PillGroup,
  density: PillDensity,
  side: PillLabelSide,
): string {
  return cn(REVEAL_WIDTH[group][density], REVEAL_OPACITY[group], REVEAL_PADDING[group][side])
}
