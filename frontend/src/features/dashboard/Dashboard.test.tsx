import { fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useActivity: vi.fn(),
  useServiceStatuses: vi.fn(),
  useCheckServiceStatuses: vi.fn(),
}))

import {
  useActivity,
  useCheckServiceStatuses,
  useServiceStatuses,
} from "@/shared/lib/queries"
import { Dashboard } from "@/features/dashboard/Dashboard"
import type { ActivityEntry, ServicesStatusResponse } from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"

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
  it("shows a loading placeholder while the activity query is loading", () => {
    vi.mocked(useActivity).mockReturnValue(queryResult<ActivityEntry[]>(undefined, true))

    render(<Dashboard />)

    expect(screen.getByText("Loading activity…")).toBeInTheDocument()
  })

  it("shows an empty feed when settled but unpopulated", () => {
    vi.mocked(useActivity).mockReturnValue(queryResult<ActivityEntry[]>([], false))

    render(<Dashboard />)

    expect(screen.getByText("No activity recorded yet.")).toBeInTheDocument()
  })

  it("renders a newest-first activity feed", () => {
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

  it("toggles the activity feed with the keyboard and ignores other keys", () => {
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>(
        [{ id: 1, ts: "2024-01-01T10:00:00Z", action: "Requested", detail: "Dune" }],
        false,
      ),
    )

    render(<Dashboard />)
    const header = screen.getByRole("button", { name: /recent activity/i })
    expect(screen.getByRole("listitem")).toBeInTheDocument()

    // A non-activating key leaves the feed open.
    fireEvent.keyDown(header, { key: "a" })
    expect(screen.getByRole("listitem")).toBeInTheDocument()

    // Enter collapses it.
    fireEvent.keyDown(header, { key: "Enter" })
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument()

    // Space expands it again.
    fireEvent.keyDown(header, { key: " " })
    expect(screen.getByRole("listitem")).toBeInTheDocument()
  })

  it("renders integration status cards", () => {
    vi.mocked(useServiceStatuses).mockReturnValue(
      queryResult(
        {
          interval_seconds: 60,
          last_check_at: "2026-06-23T13:22:46Z",
          services: {
            trakt: { ok: true, detail: "Connected", checked_at: "2026-06-23T13:22:46Z" },
            seer: {
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
    expect(screen.getByText("Seer")).toBeInTheDocument()
  })

  it("triggers a fresh check when 'Check now' is clicked", async () => {
    const user = userEvent.setup()
    vi.mocked(useActivity).mockReturnValue(queryResult<ActivityEntry[]>([], false))

    render(<Dashboard />)
    await user.click(screen.getByRole("button", { name: /check now/i }))

    expect(checkNowMutate).toHaveBeenCalledTimes(1)
  })

  it("defaults services and spins the button while a check is pending", () => {
    vi.mocked(useActivity).mockReturnValue(queryResult<ActivityEntry[]>([], false))
    // No service-status snapshot at all: `services` falls back to an empty map
    // and `lastCheck` is undefined.
    vi.mocked(useServiceStatuses).mockReturnValue(
      queryResult<ServicesStatusResponse>(undefined, false),
    )
    vi.mocked(useCheckServiceStatuses).mockReturnValue({
      mutate: checkNowMutate,
      isPending: true,
    } as never)

    render(<Dashboard />)
    // Renders without a snapshot (services defaults to an empty map) and the
    // pending check disables and spins the button.
    expect(screen.getByText("Integrations")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /check now/i })).toBeDisabled()
  })
})
