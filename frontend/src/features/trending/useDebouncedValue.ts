import { useEffect, useState } from "react"

/**
 * Return `value` once it has stopped changing for `delayMs`. Each change
 * restarts the timer, and the pending timer is cleared on change and unmount,
 * so only the settled value is ever published.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return debounced
}
