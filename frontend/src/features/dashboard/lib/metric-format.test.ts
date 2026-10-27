import { describe, expect, it } from "vitest"

import { formatMetricValue } from "@/features/dashboard/lib/metric-format"

describe("formatMetricValue", () => {
  it("renders an unavailable value as an em dash", () => {
    expect(formatMetricValue(null, "count")).toBe("—")
    expect(formatMetricValue(null, "bytes")).toBe("—")
  })

  it("formats bytes as a binary size", () => {
    expect(formatMetricValue(0, "bytes")).toBe("0 B")
    expect(formatMetricValue(1.5 * 1024 ** 4, "bytes")).toBe("1.5 TB")
  })

  it("formats speeds with one decimal", () => {
    expect(formatMetricValue(38.64, "mbps")).toBe("38.6 MB/s")
    expect(formatMetricValue(0, "mbps")).toBe("0.0 MB/s")
  })

  it("formats counts as grouped whole numbers", () => {
    expect(formatMetricValue(2236, "count")).toBe((2236).toLocaleString())
    expect(formatMetricValue(4.6, "count")).toBe("5")
  })
})
