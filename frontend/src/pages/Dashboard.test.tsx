import { render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/lib/queries", () => ({
  useStatus: vi.fn(),
  useActivity: vi.fn(),
}))

import { useActivity, useStatus } from "@/lib/queries"
import { Dashboard } from "@/pages/Dashboard"
import type { ActivityEntry, Status } from "@/lib/api"
import { queryResult } from "@/test/mock-query"

const loadedStatus: Status = {
  dry_run: false,
  trakt_connected: true,
  counts: { synced: 5, requested: 4, available: 3, removed: 2 },
}

describe("Dashboard", () => {
  it("shows placeholders while the queries are loading", () => {
    vi.mocked(useStatus).mockReturnValue(queryResult<Status>(undefined, true))
    vi.mocked(useActivity).mockReturnValue(queryResult<ActivityEntry[]>(undefined, true))

    render(<Dashboard />)

    expect(screen.getAllByText("–")).toHaveLength(4)
    expect(screen.getByText("Loading activity…")).toBeInTheDocument()
  })

  it("shows placeholders and an empty feed when settled but unpopulated", () => {
    vi.mocked(useStatus).mockReturnValue(queryResult<Status>(undefined, false))
    vi.mocked(useActivity).mockReturnValue(queryResult<ActivityEntry[]>([], false))

    render(<Dashboard />)

    expect(screen.getAllByText("–")).toHaveLength(4)
    expect(screen.getByText("No activity recorded yet.")).toBeInTheDocument()
  })

  it("renders counts and a newest-first activity feed", () => {
    vi.mocked(useStatus).mockReturnValue(queryResult<Status>(loadedStatus, false))
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>(
        [
          { id: 1, ts: "2024-01-01T10:00:00Z", action: "Older", detail: "first" },
          { id: 2, ts: "not-a-date", action: "Newer", detail: "second" },
        ],
        false,
      ),
    )

    render(<Dashboard />)

    expect(screen.getByText("5")).toBeInTheDocument()

    const entries = screen.getAllByRole("listitem")
    // Sorted by id descending: entry 2 ("Newer") comes first.
    expect(within(entries[0]).getByText("Newer")).toBeInTheDocument()
    expect(within(entries[1]).getByText("Older")).toBeInTheDocument()
    // An unparseable timestamp falls back to the raw string.
    expect(screen.getByText("not-a-date")).toBeInTheDocument()
  })
})
