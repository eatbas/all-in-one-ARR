import { describe, expect, it } from "vitest"

import {
  displayTitle,
  formatBytes,
  formatNextSync,
  formatRelativeTime,
  formatTimestamp,
  formatYear,
} from "@/shared/lib/format"

describe("displayTitle", () => {
  it("returns the title when present", () => {
    expect(displayTitle("Dune")).toBe("Dune")
  })

  it("falls back to 'Untitled' when the title is null", () => {
    expect(displayTitle(null)).toBe("Untitled")
  })
})

describe("formatYear", () => {
  it("returns the year as a string when present", () => {
    expect(formatYear(2021)).toBe("2021")
  })

  it("falls back to an em dash when the year is null", () => {
    expect(formatYear(null)).toBe("—")
  })
})

describe("formatBytes", () => {
  it("renders zero bytes explicitly", () => {
    expect(formatBytes(0)).toBe("0 B")
  })

  it("renders bytes below the KB threshold", () => {
    expect(formatBytes(512)).toBe("512 B")
  })

  it("renders kilobytes with one decimal", () => {
    expect(formatBytes(1536)).toBe("1.5 KB")
  })

  it("renders megabytes with one decimal", () => {
    expect(formatBytes(2 * 1024 * 1024)).toBe("2.0 MB")
  })
})

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

const NOW = new Date("2024-06-01T12:00:00.000Z")
const ago = (ms: number) => new Date(NOW.getTime() - ms).toISOString()
const ahead = (ms: number) => new Date(NOW.getTime() + ms).toISOString()
const MIN = 60_000
const HOUR = 60 * MIN
const DAY = 24 * HOUR
const WEEK = 7 * DAY

describe("formatRelativeTime", () => {
  it("returns the raw value when the timestamp cannot be parsed", () => {
    expect(formatRelativeTime("not-a-date", NOW)).toBe("not-a-date")
  })

  it("reports sub-minute differences as 'just now'", () => {
    expect(formatRelativeTime(ago(30_000), NOW)).toBe("just now")
  })

  it("reports minutes", () => {
    expect(formatRelativeTime(ago(45 * MIN), NOW)).toBe("45 min ago")
  })

  it("reports hours with singular and plural units", () => {
    expect(formatRelativeTime(ago(HOUR), NOW)).toBe("1 hour ago")
    expect(formatRelativeTime(ago(3 * HOUR), NOW)).toBe("3 hours ago")
  })

  it("reports days with singular and plural units", () => {
    expect(formatRelativeTime(ago(DAY), NOW)).toBe("1 day ago")
    expect(formatRelativeTime(ago(3 * DAY), NOW)).toBe("3 days ago")
  })

  it("reports weeks with singular and plural units", () => {
    expect(formatRelativeTime(ago(WEEK), NOW)).toBe("1 week ago")
    expect(formatRelativeTime(ago(2 * WEEK), NOW)).toBe("2 weeks ago")
  })
})

describe("formatNextSync", () => {
  it("renders an em dash when the next sync is unknown", () => {
    expect(formatNextSync(null, NOW)).toBe("—")
  })

  it("returns the raw value when the timestamp cannot be parsed", () => {
    expect(formatNextSync("not-a-date", NOW)).toBe("not-a-date")
  })

  it("reports an overdue sync as 'due now'", () => {
    expect(formatNextSync(ago(MIN), NOW)).toBe("due now")
  })

  it("rounds a sub-minute countdown up to one minute", () => {
    expect(formatNextSync(ahead(30_000), NOW)).toBe("in 1 min")
  })

  it("reports minutes until the next sync", () => {
    expect(formatNextSync(ahead(12 * MIN), NOW)).toBe("in 12 min")
  })

  it("reports hours with singular and plural units", () => {
    expect(formatNextSync(ahead(HOUR), NOW)).toBe("in 1 hour")
    expect(formatNextSync(ahead(3 * HOUR), NOW)).toBe("in 3 hours")
  })
})
