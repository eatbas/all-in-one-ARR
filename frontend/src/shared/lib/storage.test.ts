import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { readStoredItem, writeStoredItem } from "@/shared/lib/storage"

describe("storage helpers", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("returns the default when the key is absent", () => {
    expect(readStoredItem("missing", "fallback", () => undefined)).toBe(
      "fallback",
    )
  })

  it("parses and returns a stored value", () => {
    localStorage.setItem("key", "42")
    expect(readStoredItem("key", 0, Number)).toBe(42)
  })

  it("returns the default when parsing fails", () => {
    localStorage.setItem("key", "not-a-number")
    expect(
      readStoredItem("key", 7, (raw) => {
        const value = Number(raw)
        return Number.isNaN(value) ? undefined : value
      }),
    ).toBe(7)
  })

  it("writes a serialised value to localStorage", () => {
    writeStoredItem("key", { value: true }, (v) => JSON.stringify(v))
    expect(localStorage.getItem("key")).toBe('{"value":true}')
  })

  it("survives reading when accessing localStorage throws", () => {
    const original = Object.getOwnPropertyDescriptor(window, "localStorage")
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get: () => {
        throw new DOMException("Storage disabled", "SecurityError")
      },
    })
    try {
      expect(readStoredItem("key", "fallback", () => "parsed")).toBe("fallback")
    } finally {
      if (original) Object.defineProperty(window, "localStorage", original)
    }
  })

  it("survives reading when getItem throws", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new DOMException("Storage denied", "SecurityError")
      },
      setItem: vi.fn(),
    })
    expect(readStoredItem("key", "fallback", () => "parsed")).toBe("fallback")
  })

  it("no-ops writing when setItem throws", () => {
    vi.stubGlobal("localStorage", {
      getItem: vi.fn(),
      setItem: () => {
        throw new DOMException("Quota exceeded", "QuotaExceededError")
      },
    })
    expect(() => writeStoredItem("key", "value")).not.toThrow()
  })
})
