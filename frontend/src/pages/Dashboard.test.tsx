import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/lib/queries", () => ({
  useStatus: vi.fn(),
  useActivity: vi.fn(),
  useServiceStatuses: vi.fn(),
  useCheckServiceStatuses: vi.fn(),
}))

import {
  useActivity,
  useCheckServiceStatuses,
  useServiceStatuses,
  useStatus,
} from "@/lib/queries"
import { Dashboard } from "@/pages/Dashboard"
import type { ActivityEntry, Status } from "@/lib/api"
import { queryResult } from "@/test/mock-query"

const loadedStatus: Status = {
  dry_run: false,
  trakt_connected: true,
  counts: { synced: 5, requested: 4, available: 3, removed: 2 },
}

const emptyServiceStatuses = {
  interval_seconds: 60,
  last_check_at: null,
  services: {},
}

const checkNowMutate = vi.fn()

describe("Dashboard", () => {
  beforeEach(() => {
    checkNowMutate.mockClear()
    vi.mocked(useServiceStatuses).mockReturnValue(
      queryResult(emptyServiceStatuses, false),
    )
    vi.mocked(useCheckServiceStatuses).mockReturnValue({
      mutate: checkNowMutate,
      isPending: false,
    } as never)
  })
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

  it("collapses and expands the activity feed when the header is clicked", async () => {
    const user = userEvent.setup()
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>(
        [{ id: 1, ts: "2024-01-01T10:00:00Z", action: "Requested", detail: "Dune" }],
        false,
      ),
    )

    render(<Dashboard />)
    expect(screen.getByRole("listitem")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /recent activity/i }))

    expect(screen.queryByRole("listitem")).not.toBeInTheDocument()
    expect(screen.getByText("Show")).toBeInTheDocument()
  })

  it("renders integration status cards", () => {
    vi.mocked(useServiceStatuses).mockReturnValue(
      queryResult(
        {
          interval_seconds: 60,
          last_check_at: "2026-06-23T13:22:46Z",
          services: {
            trakt: { ok: true, detail: "Connected", checked_at: "2026-06-23T13:22:46Z" },
            jellyseerr: {
              ok: false,
              detail: "Refused",
              checked_at: "2026-06-23T13:22:46Z",
            },
          },
        },
        false,
      ),
    )

    render(<Dashboard />)
    expect(screen.getByText("Integrations")).toBeInTheDocument()
    expect(screen.getByText("Trakt")).toBeInTheDocument()
    expect(screen.getByText("Jellyseerr")).toBeInTheDocument()
  })

  it("triggers a fresh check when 'Check now' is clicked", async () => {
    const user = userEvent.setup()
    vi.mocked(useStatus).mockReturnValue(queryResult<Status>(loadedStatus, false))
    vi.mocked(useActivity).mockReturnValue(queryResult<ActivityEntry[]>([], false))

    render(<Dashboard />)
    await user.click(screen.getByRole("button", { name: /check now/i }))

    expect(checkNowMutate).toHaveBeenCalledTimes(1)
  })
})
