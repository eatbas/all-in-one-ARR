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
  7: "h-7",
  8: "h-6",
  9: "h-6",
  10: "h-6",
  11: "h-6",
}
const SLOT_SIZE: Record<PillDensity, string> = {
  5: "size-8",
  6: "size-7",
  7: "size-7",
  8: "size-6",
  9: "size-6",
  10: "size-6",
  11: "size-6",
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

  it("clamps the dense grids at the h-6 pill instead of shrinking further", () => {
    // Regression: 8–11 once shrank all the way to a 16px shell with an 8px
    // glyph, which was unreadable and untappable. Dense grids now clamp at
    // the density-7 treatment (a 24px shell — still only about a quarter of
    // the narrowest poster's width).
    expect(pillShell(5)).toContain("h-8")
    expect(pillShell(7)).toContain("h-7")
    expect(pillShell(8)).toContain("h-6")
    expect(pillShell(11)).toBe(pillShell(8))
    expect(pillIcon(7)).toBe("size-3.5")
    expect(pillIcon(11)).toBe("size-3")
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
