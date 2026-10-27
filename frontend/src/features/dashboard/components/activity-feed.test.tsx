import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useActivity: vi.fn(),
}))

import type { ActivityEntry } from "@/shared/lib/api"
import { useActivity } from "@/shared/lib/queries"
import { queryResult } from "@/shared/test/mock-query"
import { ActivityFeed } from "@/features/dashboard/components/activity-feed"

function activityEntries(count: number): ActivityEntry[] {
  return Array.from({ length: count }, (_, index) => {
    const id = index + 1
    return {
      id,
      ts: `2024-01-${String((id % 28) + 1).padStart(2, "0")}T10:00:00Z`,
      action: `Action ${id}`,
      detail: `Detail ${id}`,
    }
  })
}

function mockActivity(entries: ActivityEntry[] | undefined, loading = false) {
  vi.mocked(useActivity).mockReturnValue(queryResult(entries, loading))
}

describe("ActivityFeed", () => {
  beforeEach(() => {
    mockActivity([])
  })

  it("is always visible with no collapse toggle", () => {
    mockActivity(activityEntries(1))
    render(<ActivityFeed />)

    expect(screen.getByText("Recent activity")).toBeInTheDocument()
    expect(
      screen.getByText("Recent meaningful app activity from the last 15 days."),
    ).toBeInTheDocument()
    expect(screen.getByRole("listitem")).toBeInTheDocument()
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
    expect(screen.queryByText("Show")).not.toBeInTheDocument()
  })

  it("shows a loading placeholder", () => {
    mockActivity(undefined, true)
    render(<ActivityFeed />)

    expect(screen.getByText("Loading activity…")).toBeInTheDocument()
  })

  it("shows an empty feed when settled but unpopulated", () => {
    mockActivity(undefined)
    render(<ActivityFeed />)

    expect(screen.getByText("No activity recorded yet.")).toBeInTheDocument()
  })

  it("renders newest first and falls back to raw timestamps", () => {
    mockActivity([
      { id: 1, ts: "2024-01-01T10:00:00Z", action: "Older", detail: "first" },
      { id: 2, ts: "not-a-date", action: "Newer", detail: "second" },
    ])
    render(<ActivityFeed />)

    const entries = screen.getAllByRole("listitem")
    expect(within(entries[0]).getByText("Newer")).toBeInTheDocument()
    expect(within(entries[1]).getByText("Older")).toBeInTheDocument()
    expect(screen.getByText("not-a-date")).toBeInTheDocument()
    // A single page needs no pager.
    expect(screen.queryByText(/Page 1 of/)).not.toBeInTheDocument()
  })

  it("keeps only the newest 50 entries", () => {
    mockActivity(activityEntries(60))
    render(<ActivityFeed />)

    expect(screen.getByText("Showing 1–5 of 50")).toBeInTheDocument()
    expect(screen.getByText("Page 1 of 10")).toBeInTheDocument()
    expect(screen.getByText("Action 60")).toBeInTheDocument()
  })

  it("pages through entries within the previous and next bounds", async () => {
    const user = userEvent.setup()
    mockActivity(activityEntries(6))
    render(<ActivityFeed />)

    expect(screen.getAllByRole("listitem")).toHaveLength(5)
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled()

    await user.click(screen.getByRole("button", { name: "Next page" }))

    const entries = screen.getAllByRole("listitem")
    expect(entries).toHaveLength(1)
    expect(within(entries[0]).getByText("Action 1")).toBeInTheDocument()
    expect(screen.getByText("Showing 6–6 of 6")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled()

    await user.click(screen.getByRole("button", { name: "Previous page" }))
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument()
  })

  it("clamps the page when the feed shrinks", async () => {
    const user = userEvent.setup()
    mockActivity(activityEntries(6))
    const { rerender } = render(<ActivityFeed />)
    await user.click(screen.getByRole("button", { name: "Next page" }))
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument()

    mockActivity(activityEntries(2))
    rerender(<ActivityFeed />)

    const entries = screen.getAllByRole("listitem")
    expect(entries).toHaveLength(2)
    expect(within(entries[0]).getByText("Action 2")).toBeInTheDocument()
  })
})
