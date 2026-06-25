import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useStatus: vi.fn(),
}))

import { useStatus } from "@/shared/lib/queries"
import { SyncStats } from "@/features/list-syncarr/components/sync-stats"
import type { Status } from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"

const loadedStatus: Status = {
  trakt_connected: true,
  counts: { synced: 5, requested: 4, available: 3, removed: 2 },
}

describe("SyncStats", () => {
  it("shows placeholders while the status is loading", () => {
    vi.mocked(useStatus).mockReturnValue(queryResult<Status>(undefined, true))

    render(<SyncStats />)

    expect(screen.getAllByText("–")).toHaveLength(4)
  })

  it("shows placeholders when settled without a snapshot", () => {
    vi.mocked(useStatus).mockReturnValue(queryResult<Status>(undefined, false))

    render(<SyncStats />)

    expect(screen.getAllByText("–")).toHaveLength(4)
  })

  it("renders the aggregate counts once loaded", () => {
    vi.mocked(useStatus).mockReturnValue(queryResult<Status>(loadedStatus, false))

    render(<SyncStats />)

    expect(screen.getByText("Synced")).toBeInTheDocument()
    expect(screen.getByText("5")).toBeInTheDocument()
    expect(screen.getByText("4")).toBeInTheDocument()
    expect(screen.getByText("3")).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
  })
})
