import { useState } from "react"

import { Pagination } from "@/shared/components/pagination/pagination"
import { pageCount } from "@/shared/components/pagination/pagination-utils"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import type { ActivityEntry } from "@/shared/lib/api"
import { formatTimestamp } from "@/shared/lib/format"
import { useActivity } from "@/shared/lib/queries"

const ACTIVITY_PAGE_SIZE = 5
const ACTIVITY_LIMIT = 50

/** The newest {@link ACTIVITY_LIMIT} entries, newest first. */
function newestActivity(entries: ActivityEntry[]): ActivityEntry[] {
  return entries
    .slice()
    .sort((a, b) => b.id - a.id)
    .slice(0, ACTIVITY_LIMIT)
}

/** Always-visible recent activity, five entries per page. */
export function ActivityFeed() {
  const { data: activity, isLoading } = useActivity()
  const [page, setPage] = useState(1)

  const entries = newestActivity(activity ?? [])
  const totalPages = pageCount(entries.length, ACTIVITY_PAGE_SIZE)
  // Clamp when the feed shrinks below the page the user was on.
  const currentPage = Math.min(page, totalPages)
  const visible = entries.slice(
    (currentPage - 1) * ACTIVITY_PAGE_SIZE,
    currentPage * ACTIVITY_PAGE_SIZE,
  )

  return (
    <Card aria-labelledby="activity-title">
      <CardHeader className="pb-0">
        <CardTitle id="activity-title">Recent activity</CardTitle>
        <CardDescription>
          Recent meaningful app activity from the last 15 days.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading activity…</p>
        ) : entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No activity recorded yet.
          </p>
        ) : (
          <div className="flex flex-col gap-4">
            <ul className="divide-y">
              {visible.map((entry) => (
                <li
                  key={entry.id}
                  className="flex items-start justify-between gap-4 py-3 first:pt-0 last:pb-0"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{entry.action}</p>
                    <p className="truncate text-sm text-muted-foreground">
                      {entry.detail}
                    </p>
                  </div>
                  <time
                    dateTime={entry.ts}
                    className="shrink-0 text-xs text-muted-foreground"
                  >
                    {formatTimestamp(entry.ts)}
                  </time>
                </li>
              ))}
            </ul>
            {totalPages > 1 ? (
              <Pagination
                page={currentPage}
                pageSize={ACTIVITY_PAGE_SIZE}
                totalItems={entries.length}
                onPageChange={setPage}
              />
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
