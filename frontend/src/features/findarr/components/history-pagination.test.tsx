import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { HistoryPagination } from "@/features/findarr/components/history-pagination"

describe("HistoryPagination", () => {
  it("reports the visible range and page position", () => {
    render(
      <HistoryPagination page={1} pageSize={10} totalItems={25} onPageChange={vi.fn()} />,
    )
    expect(screen.getByText("Showing 1–10 of 25")).toBeInTheDocument()
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument()
  })

  it("narrows the range on the final, partially filled page", () => {
    render(
      <HistoryPagination page={3} pageSize={10} totalItems={25} onPageChange={vi.fn()} />,
    )
    expect(screen.getByText("Showing 21–25 of 25")).toBeInTheDocument()
    expect(screen.getByText("Page 3 of 3")).toBeInTheDocument()
  })

  it("disables Previous on the first page and enables Next", () => {
    render(
      <HistoryPagination page={1} pageSize={10} totalItems={25} onPageChange={vi.fn()} />,
    )
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Next page" })).toBeEnabled()
  })

  it("disables Next on the last page and enables Previous", () => {
    render(
      <HistoryPagination page={3} pageSize={10} totalItems={25} onPageChange={vi.fn()} />,
    )
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Previous page" })).toBeEnabled()
  })

  it("requests the next page", async () => {
    const onPageChange = vi.fn()
    const user = userEvent.setup()
    render(
      <HistoryPagination
        page={1}
        pageSize={10}
        totalItems={25}
        onPageChange={onPageChange}
      />,
    )
    await user.click(screen.getByRole("button", { name: "Next page" }))
    expect(onPageChange).toHaveBeenCalledWith(2)
  })

  it("requests the previous page", async () => {
    const onPageChange = vi.fn()
    const user = userEvent.setup()
    render(
      <HistoryPagination
        page={2}
        pageSize={10}
        totalItems={25}
        onPageChange={onPageChange}
      />,
    )
    await user.click(screen.getByRole("button", { name: "Previous page" }))
    expect(onPageChange).toHaveBeenCalledWith(1)
  })
})
