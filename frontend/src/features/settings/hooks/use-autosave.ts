import { useEffect, useRef } from "react"

const AUTOSAVE_DELAY_MS = 800

/**
 * Debounced autosave helper. Schedules `mutate(body)` after `AUTOSAVE_DELAY_MS`
 * whenever `body` is non-null, but skips scheduling while a matching save is
 * already in-flight. It also suppresses re-submission of an identical body
 * after a failed save settles back to `isPending === false`, preventing the
 * same failed payload from being retried automatically every debounce cycle.
 */
export function useAutosave<TBody>({
  body,
  draftRevision,
  mutate,
  isPending,
  onSuccess,
}: {
  body: TBody | null
  draftRevision: number
  mutate: (body: TBody, options?: { onSuccess?: () => void }) => void
  isPending: boolean
  onSuccess: () => void
}): void {
  const lastSubmittedRevisionRef = useRef<number | null>(null)

  useEffect(() => {
    if (!body) {
      lastSubmittedRevisionRef.current = null
      return
    }
    if (isPending) return

    // Revisions are non-secret edit counters, so failed-save suppression does
    // not retain Trakt secrets or service API keys in component refs.
    if (draftRevision === lastSubmittedRevisionRef.current) return

    const timer = window.setTimeout(() => {
      lastSubmittedRevisionRef.current = draftRevision
      mutate(body, { onSuccess })
    }, AUTOSAVE_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [body, draftRevision, isPending, mutate, onSuccess])
}
