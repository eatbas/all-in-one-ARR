import { describe, expect, it } from "vitest"

import { formatTimestamp } from "@/lib/format"

describe("formatTimestamp", () => {
  it("formats a parseable ISO timestamp into a localised string", () => {
    const formatted = formatTimestamp("2024-01-02T10:00:00Z")
    expect(formatted).not.toBe("2024-01-02T10:00:00Z")
    expect(formatted.length).toBeGreaterThan(0)
  })

  it("returns the raw value when the timestamp cannot be parsed", () => {
    expect(formatTimestamp("not-a-date")).toBe("not-a-date")
  })
})
