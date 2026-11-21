import { TriangleAlertIcon } from "lucide-react"

import { Card, CardContent } from "@/shared/components/ui/card"
import { formatRelativeTime, formatTimestamp } from "@/shared/lib/format"

interface StaleBannerProps {
  /** Why the last refresh failed. */
  error: string
  /** When the failing refresh was attempted, if known. */
  lastAttemptAt: string | null
  /** When the results on the page were produced, if ever. */
  lastSuccessAt: string | null
}

/**
 * Amber warning shown when the last refresh failed: the page keeps the
 * previous results (and the nav badge keeps its count) until a refresh works.
 */
export function StaleBanner({
  error,
  lastAttemptAt,
  lastSuccessAt,
}: StaleBannerProps) {
  const when = lastAttemptAt ? ` ${formatRelativeTime(lastAttemptAt)}` : ""
  const kept = lastSuccessAt
    ? `; showing results from ${formatTimestamp(lastSuccessAt)}.`
    : "."

  return (
    <Card role="alert" className="border-amber-500/45 py-4">
      <CardContent className="flex items-start gap-3">
        <TriangleAlertIcon
          aria-hidden="true"
          className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400"
        />
        <div className="grid gap-1">
          <p className="text-sm font-semibold">Results may be out of date</p>
          <p className="text-sm text-muted-foreground">
            Last refresh failed{when}: {error.replace(/\.$/, "")}
            {kept}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
