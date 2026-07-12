import { useEffect, useRef, useState } from "react"

/** Rows revealed per infinite-scroll batch — also the initial number of rows. */
const ROWS_PER_BATCH = 3

/**
 * Bounded reveal for a poster grid. Exposes the number of items currently shown,
 * whether a sentinel should still render, a ref for that sentinel, and a reset
 * helper that collapses back to the first batch (optionally at a new row width).
 *
 * The observer is recreated each time the reveal grows so a sentinel remaining
 * in view after an expansion keeps loading batches until it is pushed off-screen
 * or the list ends. `Math.min` and the `hasMore` guard bound growth to the
 * fetched list.
 */
export function usePosterReveal(perRow: number, total: number) {
  const [visibleCount, setVisibleCount] = useState(ROWS_PER_BATCH * perRow)
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  function resetReveal(nextPerRow: number = perRow) {
    setVisibleCount(ROWS_PER_BATCH * nextPerRow)
  }

  useEffect(() => {
    if (visibleCount >= total) return
    const node = sentinelRef.current
    /* v8 ignore next -- hasMore renders and attaches the sentinel before this effect runs. */
    if (!node) return
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) {
        setVisibleCount((count) =>
          Math.min(count + ROWS_PER_BATCH * perRow, total),
        )
      }
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [perRow, total, visibleCount])

  const hasMore = visibleCount < total

  return { visibleCount, hasMore, sentinelRef, resetReveal }
}
