import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useFindarrHistory: vi.fn(),
}))

import { useFindarrHistory } from "@/shared/lib/queries"
import { History } from "@/features/findarr/tabs/History"
import type { FindarrHistoryEntry } from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"

beforeEach(() => {
  vi.mocked(useFindarrHistory).mockReturnValue(queryResult<FindarrHistoryEntry[]>([]))
})

describe("Findarr History tab", () => {
  it("shows a loading state until history arrives", () => {
    vi.mocked(useFindarrHistory).mockReturnValue(
      queryResult<FindarrHistoryEntry[]>(undefined, true),
    )
    render(<History />)
    expect(screen.getByText("Loading history…")).toBeInTheDocument()
  })

  it("shows an empty state when there is no history", () => {
    render(<History />)
    expect(screen.getByText("No Findarr history yet.")).toBeInTheDocument()
  })

  it("renders rows, falling back to the item id then 'System' for the title", () => {
    vi.mocked(useFindarrHistory).mockReturnValue(
      queryResult<FindarrHistoryEntry[]>([
        {
          id: 1, ts: "2026-06-26T20:00:00Z", app: "sonarr", mode: "missing",
          item_id: "5", title: "Pilot", status: "success", detail: "ok",
        },
        {
          id: 2, ts: "2026-06-26T20:01:00Z", app: "radarr", mode: "missing",
          item_id: "9", title: null, status: "error", detail: "boom",
        },
        {
          id: 3, ts: "2026-06-26T20:02:00Z", app: "sonarr", mode: "system",
          item_id: null, title: null, status: "success", detail: "tick",
        },
      ]),
    )
    render(<History />)
    expect(screen.getByText("Pilot")).toBeInTheDocument()
    expect(screen.getByText("9")).toBeInTheDocument() // title null -> item_id
    expect(screen.getByText("System")).toBeInTheDocument() // both null -> "System"
    expect(screen.getByText("boom")).toBeInTheDocument()
  })
})
