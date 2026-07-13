import { useState } from "react"

import { Badge } from "@/shared/components/ui/badge"
import { Pagination } from "@/shared/components/pagination/pagination"
import { pageCount } from "@/shared/components/pagination/pagination-utils"
import { DownloadRows } from "@/features/bandwidth-controllarr/components/download-rows"
import type { BandwidthQueueGroup } from "@/shared/lib/api"

/** Queue rows shown per downloader before paging. */
const QUEUE_PAGE_SIZE = 5

interface QueueGroupProps {
  label: string
  group: BandwidthQueueGroup
}

/**
 * One downloader's queue, paged {@link QUEUE_PAGE_SIZE} rows at a time. The
 * badge reports the whole queue depth rather than the rows on screen, so a
 * deep queue reads honestly while staying compact.
 */
export function QueueGroup({ label, group }: QueueGroupProps) {
  const [page, setPage] = useState(1)

  // Clamp rather than trust the stored page: the status query refetches every
  // few seconds, so a queue that drains while the user sits on a later page
  // must fall back to the last page that still exists instead of rendering
  // an empty one.
  const totalPages = pageCount(group.items.length, QUEUE_PAGE_SIZE)
  const currentPage = Math.min(page, totalPages)
  const visible = group.items.slice(
    (currentPage - 1) * QUEUE_PAGE_SIZE,
    currentPage * QUEUE_PAGE_SIZE,
  )
  const withheld = group.total - group.items.length

  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-medium">{label}</h3>
        <Badge variant="outline">{group.total}</Badge>
      </div>
      {group.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No queued downloads</p>
      ) : (
        <>
          <DownloadRows items={visible} />
          {withheld > 0 && (
            <p className="text-sm text-muted-foreground">
              {label} reports {group.total} queued; only the first{" "}
              {group.items.length} are listed here.
            </p>
          )}
          {group.items.length > QUEUE_PAGE_SIZE && (
            <Pagination
              page={currentPage}
              pageSize={QUEUE_PAGE_SIZE}
              totalItems={group.items.length}
              onPageChange={setPage}
            />
          )}
        </>
      )}
    </section>
  )
}
