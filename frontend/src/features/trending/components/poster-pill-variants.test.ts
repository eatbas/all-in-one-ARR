import { describe, expect, it } from "vitest"

import {
  pillIcon,
  pillLabelReveal,
  pillShell,
  type PillDensity,
} from "@/features/trending/components/poster-pill-variants"

const DENSITIES: PillDensity[] = [5, 6, 7, 8, 9, 10, 11]

describe("poster-pill-variants", () => {
  it("defines a shell, icon and reveal for every density 5–11", () => {
    // Every selectable posters-per-row density must resolve to a concrete size —
    // a missing entry would render `cn(undefined)` and drop the pill sizing.
    for (const density of DENSITIES) {
      expect(pillShell(density)).toMatch(/\bsize-/)
      expect(pillIcon(density)).toMatch(/\bsize-/)
      expect(pillLabelReveal("link", density, "left")).not.toBe("")
    }
  })

  it("keeps shrinking past density 7 (the 8–11 clamp is gone)", () => {
    // Regression: 8–11 used to reuse density 7's pill size, so the overlay icons
    // never shrank on the denser grids. They must now be distinctly smaller.
    expect(pillShell(5)).toContain("size-8")
    expect(pillShell(7)).toContain("size-6")
    expect(pillShell(11)).toContain("size-4")
    expect(pillShell(11)).not.toBe(pillShell(7))
    expect(pillIcon(7)).toBe("size-3")
    expect(pillIcon(11)).toBe("size-2")
  })
})
