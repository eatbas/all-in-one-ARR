import { render, screen, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useCleanarrHistory: vi.fn(),
}))

import { History } from "@/features/cleanarr/tabs/History"
import type { CleanarrHistoryEntry } from "@/shared/lib/api"
import { useCleanarrHistory } from "@/shared/lib/queries"
import { CLEANARR_HISTORY } from "@/shared/test/cleanarr-fixtures"
import { queryResult } from "@/shared/test/mock-query"

beforeEach(() => {
  vi.mocked(useCleanarrHistory).mockReturnValue(queryResult(CLEANARR_HISTORY))
})

describe("Cleanarr History tab", () => {
  it("shows a loading state", () => {
    vi.mocked(useCleanarrHistory).mockReturnValue(
      queryResult<CleanarrHistoryEntry[]>(undefined, true),
    )
    render(<History />)
    expect(screen.getByText("Loading history…")).toBeInTheDocument()
  })

  it("shows a load error", () => {
    vi.mocked(useCleanarrHistory).mockReturnValue(
      queryResult<CleanarrHistoryEntry[]>(undefined, false, {
        isError: true,
        error: new Error("down"),
      }),
    )
    render(<History />)
    expect(screen.getByText("Could not load history: down")).toBeInTheDocument()
  })

  it("shows an empty state", () => {
    vi.mocked(useCleanarrHistory).mockReturnValue(queryResult([]))
    render(<History />)
    expect(screen.getByText("No Cleanarr history yet.")).toBeInTheDocument()
  })

  it("renders rows with action pills and the dry-run marker", () => {
    render(<History />)
    const rows = screen.getAllByRole("row").slice(1)
    expect(rows).toHaveLength(2)

    const dryRun = within(rows[0])
    expect(dryRun.getByText("Sonarr")).toBeInTheDocument()
    expect(dryRun.getByText("Would remove")).toBeInTheDocument()
    expect(dryRun.getByText("Dry run")).toBeInTheDocument()
    expect(dryRun.getByText("failed import")).toBeInTheDocument()
    expect(dryRun.getByText("The.Last.of.Us.S02E03.1080p")).toHaveAttribute(
      "title",
      "The.Last.of.Us.S02E03.1080p",
    )

    const purge = within(rows[1])
    expect(purge.getByText("SABnzbd")).toBeInTheDocument()
    expect(purge.getByText("Purged")).toBeInTheDocument()
    expect(purge.queryByText("Dry run")).not.toBeInTheDocument()
    expect(purge.getAllByText("—")).toHaveLength(2)
  })
})
