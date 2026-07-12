import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  DEFAULT_LIST_SYNCARR_DENSITY,
  DEFAULT_TRENDING_DENSITY,
  GRID_COLS,
  VALID_POSTER_DENSITIES,
  readStoredDensity,
  writeStoredDensity,
} from "@/shared/components/poster-grid/poster-grid-density"

describe("poster-grid-density", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("exposes a contiguous 5–11 density allow-list", () => {
    expect(VALID_POSTER_DENSITIES).toEqual([5, 6, 7, 8, 9, 10, 11])
  })

  it("provides a Tailwind grid class for every selectable density", () => {
    for (const density of VALID_POSTER_DENSITIES) {
      expect(GRID_COLS[density]).toMatch(/^grid grid-cols-/)
      expect(GRID_COLS[density]).toContain(`lg:grid-cols-${density}`)
    }
  })

  it("restores a valid stored density", () => {
    localStorage.setItem("test-key", "9")
    expect(readStoredDensity("test-key", DEFAULT_TRENDING_DENSITY)).toBe(9)
  })

  it("falls back to the default for a missing key", () => {
    expect(readStoredDensity("missing-key", DEFAULT_LIST_SYNCARR_DENSITY)).toBe(
      8,
    )
  })

  it("falls back to the default for an invalid stored value", () => {
    localStorage.setItem("test-key", "99")
    expect(readStoredDensity("test-key", DEFAULT_TRENDING_DENSITY)).toBe(5)
  })

  it("falls back to the default for a non-numeric stored value", () => {
    localStorage.setItem("test-key", "eleven")
    expect(readStoredDensity("test-key", DEFAULT_LIST_SYNCARR_DENSITY)).toBe(8)
  })

  it("falls back to the default when localStorage is unavailable", () => {
    vi.stubGlobal("localStorage", undefined)
    expect(readStoredDensity("test-key", DEFAULT_TRENDING_DENSITY)).toBe(5)
  })

  it("writes a valid density to localStorage", () => {
    writeStoredDensity("test-key", 7)
    expect(localStorage.getItem("test-key")).toBe("7")
  })

  it("survives writing when localStorage is unavailable", () => {
    vi.stubGlobal("localStorage", undefined)
    expect(() => writeStoredDensity("test-key", 6)).not.toThrow()
  })

  it("falls back to the default when accessing localStorage throws", () => {
    const original = Object.getOwnPropertyDescriptor(window, "localStorage")
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get: () => {
        throw new DOMException("Storage disabled", "SecurityError")
      },
    })
    try {
      expect(readStoredDensity("test-key", DEFAULT_TRENDING_DENSITY)).toBe(5)
      expect(() =>
        writeStoredDensity("test-key", DEFAULT_LIST_SYNCARR_DENSITY),
      ).not.toThrow()
    } finally {
      if (original) {
        Object.defineProperty(window, "localStorage", original)
      }
    }
  })

  it("falls back to the default when getItem throws", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new DOMException("Storage denied", "SecurityError")
      },
      setItem: vi.fn(),
    })
    expect(readStoredDensity("test-key", DEFAULT_LIST_SYNCARR_DENSITY)).toBe(8)
  })

  it("no-ops when setItem throws", () => {
    vi.stubGlobal("localStorage", {
      getItem: vi.fn(),
      setItem: () => {
        throw new DOMException("Quota exceeded", "QuotaExceededError")
      },
    })
    expect(() => writeStoredDensity("test-key", 7)).not.toThrow()
  })
})
