import { useEffect, useState } from "react"

/**
 * A `Date` that advances once per second, letting relative-time labels (the
 * next-sync countdown, "last synced" text) tick live without a page refresh.
 */
export function useNow(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return now
}
