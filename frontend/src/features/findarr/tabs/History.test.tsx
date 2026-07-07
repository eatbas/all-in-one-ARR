import { render as rtlRender, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { Mock } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useFindarrHistory: vi.fn(),
  useClearFindarrHistory: vi.fn(),
}))

import { useClearFindarrHistory, useFindarrHistory } from "@/shared/lib/queries"
import { History } from "@/features/findarr/tabs/History"
import type { FindarrCountResult, FindarrHistoryEntry } from "@/shared/lib/api"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import { mutationResult, queryResult } from "@/shared/test/mock-query"

const ROWS: FindarrHistoryEntry[] = [
  {
    id: 1,
    ts: "2026-06-29T20:43:00Z",
    app: "sonarr",
    mode: "missing",
    item_id: "34451",
    title: "Avatar: The Last Airbender (2024) - S01E06 - Masks",
    status: "success",
    detail: "Triggered Sonarr missing search",
  },
  {
    id: 2,
    ts: "2026-06-29T14:00:00Z",
    app: "radarr",
    mode: "upgrade",
    item_id: "3777",
    title: "Little Brother (2026)",
    status: "error",
    detail: "boom",
  },
  {
    id: 3,
    ts: "2026-06-29T08:00:00Z",
    app: "sonarr",
    mode: "system",
    item_id: null,
    title: null,
    status: "success",
    detail: "Findarr history cleared (0 rows removed)",
  },
]

let clearMutate: Mock<() => void>

/** A run of sonarr rows titled `Show 0…Show n-1`, for pagination assertions. */
function manyRows(count: number): FindarrHistoryEntry[] {
  return Array.from({ length: count }, (_, index) => ({
    id: index + 1,
    ts: "2026-06-29T20:00:00Z",
    app: "sonarr",
    mode: "missing",
    item_id: String(index),
    title: `Show ${index}`,
    status: "success",
    detail: "ok",
  }))
}

function render(ui: ReactElement) {
  return rtlRender(<TooltipProvider>{ui}</TooltipProvider>)
}

beforeEach(() => {
  clearMutate = vi.fn()
  vi.mocked(useFindarrHistory).mockReturnValue(
    queryResult<FindarrHistoryEntry[]>(ROWS),
  )
  vi.mocked(useClearFindarrHistory).mockReturnValue(
    mutationResult<FindarrCountResult, void>(() => clearMutate(), false),
  )
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
    vi.mocked(useFindarrHistory).mockReturnValue(
      queryResult<FindarrHistoryEntry[]>([]),
    )
    render(<History />)
    expect(screen.getByText("No Findarr history yet.")).toBeInTheDocument()
  })

  it("renders the reference columns, resolving titles, operations and instances", () => {
    render(<History />)
    expect(
      screen.getByText("Avatar: The Last Airbender (2024) - S01E06 - Masks"),
    ).toBeInTheDocument()
    expect(screen.getByText("Missing")).toBeInTheDocument()
    expect(screen.getByText("Upgrade")).toBeInTheDocument()
    expect(screen.getByText("System")).toBeInTheDocument()
    // System rows surface their detail as the processed-information text.
    expect(
      screen.getByText("Findarr history cleared (0 rows removed)"),
    ).toBeInTheDocument()
    expect(screen.getByText("34451")).toBeInTheDocument()
    expect(screen.getByText("—")).toBeInTheDocument() // system row has no id
    expect(screen.getAllByText("Sonarr - Default")).toHaveLength(2)
    expect(screen.getByText("Radarr - Default")).toBeInTheDocument()
  })

  it("reveals the status and detail in the info tooltip", async () => {
    const user = userEvent.setup()
    render(<History />)
    await user.hover(
      screen.getByRole("button", {
        name: "Details for Little Brother (2026): error",
      }),
    )
    expect((await screen.findAllByText(/boom/)).length).toBeGreaterThan(0)
  })

  it("filters by instance", async () => {
    const user = userEvent.setup()
    render(<History />)
    await user.click(
      screen.getByRole("combobox", { name: "Filter by instance" }),
    )
    await user.click(screen.getByRole("option", { name: "Sonarr" }))
    expect(screen.queryByText("Little Brother (2026)")).not.toBeInTheDocument()
    expect(
      screen.getByText("Avatar: The Last Airbender (2024) - S01E06 - Masks"),
    ).toBeInTheDocument()
  })

  it("filters by search text and shows a no-match message", async () => {
    const user = userEvent.setup()
    render(<History />)
    await user.type(screen.getByLabelText("Search history"), "Avatar")
    expect(screen.queryByText("Little Brother (2026)")).not.toBeInTheDocument()
    expect(
      screen.getByText("Avatar: The Last Airbender (2024) - S01E06 - Masks"),
    ).toBeInTheDocument()

    await user.clear(screen.getByLabelText("Search history"))
    await user.type(screen.getByLabelText("Search history"), "no-such-entry")
    expect(
      screen.getByText("No entries match your filters."),
    ).toBeInTheDocument()
  })

  it("pages through history at the selected page size", async () => {
    vi.mocked(useFindarrHistory).mockReturnValue(
      queryResult<FindarrHistoryEntry[]>(manyRows(25)),
    )
    const user = userEvent.setup()
    render(<History />)

    // Drop the page size to 10, giving three pages over 25 rows.
    await user.click(screen.getByRole("combobox", { name: "Rows to show" }))
    await user.click(screen.getByRole("option", { name: "10" }))
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument()
    expect(screen.getByText("Show 0")).toBeInTheDocument()
    expect(screen.queryByText("Show 10")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Next page" }))
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument()
    expect(screen.getByText("Show 10")).toBeInTheDocument()
    expect(screen.queryByText("Show 0")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Previous page" }))
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument()
    expect(screen.getByText("Show 0")).toBeInTheDocument()
  })

  it("returns to the first page when the page size changes", async () => {
    vi.mocked(useFindarrHistory).mockReturnValue(
      queryResult<FindarrHistoryEntry[]>(manyRows(25)),
    )
    const user = userEvent.setup()
    render(<History />)

    // Default size 20 → two pages; advance to the second, then resize to 10.
    await user.click(screen.getByRole("button", { name: "Next page" }))
    expect(screen.getByText("Show 20")).toBeInTheDocument()

    await user.click(screen.getByRole("combobox", { name: "Rows to show" }))
    await user.click(screen.getByRole("option", { name: "10" }))
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument()
    expect(screen.getByText("Show 0")).toBeInTheDocument()
    expect(screen.queryByText("Show 20")).not.toBeInTheDocument()
  })

  it("returns to the first page when the instance filter changes", async () => {
    vi.mocked(useFindarrHistory).mockReturnValue(
      queryResult<FindarrHistoryEntry[]>(manyRows(25)),
    )
    const user = userEvent.setup()
    render(<History />)

    await user.click(screen.getByRole("button", { name: "Next page" }))
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument()

    await user.click(
      screen.getByRole("combobox", { name: "Filter by instance" }),
    )
    await user.click(screen.getByRole("option", { name: "Sonarr" }))
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument()
    expect(screen.getByText("Show 0")).toBeInTheDocument()
  })

  it("returns to the first page when the search text changes", async () => {
    vi.mocked(useFindarrHistory).mockReturnValue(
      queryResult<FindarrHistoryEntry[]>(manyRows(25)),
    )
    const user = userEvent.setup()
    render(<History />)

    await user.click(screen.getByRole("button", { name: "Next page" }))
    expect(screen.queryByText("Show 0")).not.toBeInTheDocument()

    await user.type(screen.getByLabelText("Search history"), "Show")
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument()
    expect(screen.getByText("Show 0")).toBeInTheDocument()
  })

  it("clears the history after confirmation", async () => {
    const user = userEvent.setup()
    render(<History />)
    await user.click(screen.getByRole("button", { name: "Clear" }))
    const dialog = screen.getByRole("alertdialog")
    await user.click(
      within(dialog).getByRole("button", { name: "Clear history" }),
    )
    expect(clearMutate).toHaveBeenCalledTimes(1)
  })

  it("disables the Clear button while a clear is pending", () => {
    vi.mocked(useClearFindarrHistory).mockReturnValue(
      mutationResult<FindarrCountResult, void>(() => clearMutate(), true),
    )
    render(<History />)
    expect(screen.getByRole("button", { name: "Clear" })).toBeDisabled()
  })
})
