import { describe, expect, it } from "vitest"

import {
  pillIcon,
  pillIconSlot,
  pillLabelReveal,
  pillShell,
  type PillDensity,
} from "@/shared/components/poster-pill/poster-pill-variants"

const DENSITIES: PillDensity[] = [5, 6, 7, 8, 9, 10, 11]
// The shell fixes only the height; the icon slot keeps the square size that
// renders the resting circle.
const SHELL_HEIGHT: Record<PillDensity, string> = {
  5: "h-8",
  6: "h-7",
  7: "h-6",
  8: "h-[22px]",
  9: "h-5",
  10: "h-[18px]",
  11: "h-4",
}
const SLOT_SIZE: Record<PillDensity, string> = {
  5: "size-8",
  6: "size-7",
  7: "size-6",
  8: "size-[22px]",
  9: "size-5",
  10: "size-[18px]",
  11: "size-4",
}

describe("poster-pill-variants", () => {
  it("defines a shell, icon and reveal for every density 5–11", () => {
    // Every selectable posters-per-row density must resolve to a concrete size —
    // a missing entry would render `cn(undefined)` and drop the pill sizing.
    for (const density of DENSITIES) {
      expect(pillShell(density)).toMatch(/\bh-/)
      expect(pillIcon(density)).toMatch(/\bsize-/)
      expect(pillLabelReveal("link", density, "left")).not.toBe("")
      expect(pillLabelReveal("delete", density, "right")).toContain(
        "group-hover/delete:",
      )
    }
  })

  it("keeps shrinking past density 7 (the 8–11 clamp is gone)", () => {
    // Regression: 8–11 used to reuse density 7's pill size, so the overlay icons
    // never shrank on the denser grids. They must now be distinctly smaller.
    expect(pillShell(5)).toContain("h-8")
    expect(pillShell(7)).toContain("h-6")
    expect(pillShell(11)).toContain("h-4")
    expect(pillShell(11)).not.toBe(pillShell(7))
    expect(pillIcon(7)).toBe("size-3")
    expect(pillIcon(11)).toBe("size-2")
  })

  it("keeps every icon slot fixed and centred inside its matching shell", () => {
    for (const density of DENSITIES) {
      expect(pillShell(density)).toContain(SHELL_HEIGHT[density])
      expect(pillIconSlot(density)).toContain(SLOT_SIZE[density])
      expect(pillIconSlot(density)).toContain("inline-grid")
      expect(pillIconSlot(density)).toContain("shrink-0")
      expect(pillIconSlot(density)).toContain("place-items-center")
    }
  })

  it("hugs its content and transitions only colours so the icon never jitters", () => {
    // The pill grows via the label's own max-width transition, not by animating
    // the shell width: a transitioned width would let justify-center re-centre
    // the icon mid-animation. The shell must stay content-sized (w-fit) and only
    // transition colours — never `transition-all` or a `w-auto` width swap.
    for (const density of DENSITIES) {
      expect(pillShell(density)).toContain("w-fit")
      expect(pillShell(density)).toContain("transition-colors")
      expect(pillShell(density)).not.toContain("transition-all")
      expect(pillShell(density)).not.toContain("w-auto")
    }
  })
})
