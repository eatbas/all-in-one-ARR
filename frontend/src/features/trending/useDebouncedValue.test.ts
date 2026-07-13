import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useDebouncedValue } from "@/features/trending/useDebouncedValue"

describe("useDebouncedValue", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("publishes a new value only after the delay elapses", () => {
    const hook = renderHook(({ value }) => useDebouncedValue(value, 300), {
      initialProps: { value: "a" },
    })
    hook.rerender({ value: "ab" })
    expect(hook.result.current).toBe("a")
    act(() => vi.advanceTimersByTime(300))
    expect(hook.result.current).toBe("ab")
  })

  it("restarts the timer on every change so only the settled value lands", () => {
    const hook = renderHook(({ value }) => useDebouncedValue(value, 300), {
      initialProps: { value: "a" },
    })
    hook.rerender({ value: "ab" })
    act(() => vi.advanceTimersByTime(200))
    hook.rerender({ value: "abc" })
    act(() => vi.advanceTimersByTime(200))
    // The intermediate value never fires; the timer restarted at "abc".
    expect(hook.result.current).toBe("a")
    act(() => vi.advanceTimersByTime(100))
    expect(hook.result.current).toBe("abc")
  })

  it("clears the pending timer on unmount", () => {
    const hook = renderHook(({ value }) => useDebouncedValue(value, 300), {
      initialProps: { value: "a" },
    })
    hook.rerender({ value: "ab" })
    hook.unmount()
    // Advancing past the delay after unmount must not fire the stale timer.
    act(() => vi.advanceTimersByTime(300))
    expect(vi.getTimerCount()).toBe(0)
  })
})
