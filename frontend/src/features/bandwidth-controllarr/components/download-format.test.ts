import { describe, expect, it } from "vitest"

import {
  formatEta,
  formatFinished,
  formatProgress,
  formatSize,
  formatSpeed,
  rowKey,
} from "@/features/bandwidth-controllarr/components/download-format"
import { downloadItem as item } from "@/features/bandwidth-controllarr/components/download-test-fixtures"

describe("formatSpeed", () => {
  it("renders a downloader that reports no speed as an em dash", () => {
    // An idle, queued or finished row must not read as a misleading zero.
    expect(formatSpeed(null)).toBe("—")
  })

  it("renders megabyte rates with two decimals", () => {
    expect(formatSpeed(1.25)).toBe("1.25 MB/s")
    expect(formatSpeed(12)).toBe("12.00 MB/s")
  })

  it("renders sub-megabyte rates in KB/s rather than 0.00 MB/s", () => {
    expect(formatSpeed(0.5)).toBe("512 KB/s")
    expect(formatSpeed(0.01)).toBe("10 KB/s")
    expect(formatSpeed(0)).toBe("0 KB/s")
  })
})

describe("formatEta", () => {
  it("renders each unit boundary", () => {
    expect(formatEta(null)).toBe("—")
    expect(formatEta(45)).toBe("45s")
    expect(formatEta(125)).toBe("2m")
    expect(formatEta(3600)).toBe("1h")
    expect(formatEta(3720)).toBe("1h 2m")
  })
})

describe("formatProgress", () => {
  it("drops the decimal for whole percentages and keeps it otherwise", () => {
    expect(formatProgress(null)).toBe("—")
    expect(formatProgress(50)).toBe("50%")
    expect(formatProgress(12.5)).toBe("12.5%")
  })
})

describe("formatSize", () => {
  it("prefers the downloader's own label", () => {
    expect(formatSize(item({ size_label: "2.0 GB" }))).toBe("2.0 GB")
  })

  it("falls back to the byte count, then to an em dash", () => {
    expect(formatSize(item({ size_label: null, size_bytes: 1024 }))).toBe(
      "1.0 KB",
    )
    expect(formatSize(item({ size_label: null, size_bytes: null }))).toBe("—")
  })
})

describe("formatFinished", () => {
  it("renders a relative time, or an em dash when unfinished", () => {
    const completedAt = new Date(Date.now() - 125 * 60_000).toISOString()
    expect(formatFinished(completedAt)).toBe("2 hours ago")
    expect(formatFinished(null)).toBe("—")
  })
})

describe("rowKey", () => {
  it("distinguishes the same id across clients and lists", () => {
    const queued = item({ id: "same", added_at: "2026-06-26T20:00:00Z" })
    const finished = item({
      id: "same",
      completed_at: "2026-06-26T21:00:00Z",
    })
    expect(rowKey(queued, 0)).not.toBe(rowKey(finished, 0))
  })

  it("falls back to the index when the row carries no timestamps", () => {
    const undated = item({ added_at: null, completed_at: null })
    expect(rowKey(undated, 3)).toBe("qbittorrent-download-1-3")
  })
})
