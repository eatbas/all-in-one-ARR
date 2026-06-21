import { describe, expect, it } from "vitest"

import { cn } from "@/lib/utils"

describe("cn", () => {
  it("joins multiple class name arguments", () => {
    expect(cn("px-2", "font-medium")).toBe("px-2 font-medium")
  })

  it("drops falsy and conditional inputs (clsx semantics)", () => {
    expect(cn("a", false, undefined, null, "c")).toBe("a c")
  })

  it("accepts arrays and conditional objects", () => {
    expect(cn(["a", "b"], { c: true, d: false })).toBe("a b c")
  })

  it("merges conflicting Tailwind utilities, last one winning", () => {
    expect(cn("p-2", "p-4")).toBe("p-4")
    expect(cn("text-sm", "text-lg")).toBe("text-lg")
  })
})
