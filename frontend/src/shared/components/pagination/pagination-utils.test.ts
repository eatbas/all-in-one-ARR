import { describe, expect, it } from "vitest"

import { pageCount } from "@/shared/components/pagination/pagination-utils"

describe("pageCount", () => {
  it("returns at least one page for an empty list", () => {
    expect(pageCount(0, 10)).toBe(1)
  })

  it("returns a single page when the rows fit exactly", () => {
    expect(pageCount(10, 10)).toBe(1)
  })

  it("rounds a partial final page up", () => {
    expect(pageCount(25, 10)).toBe(3)
    expect(pageCount(5, 10)).toBe(1)
  })
})
