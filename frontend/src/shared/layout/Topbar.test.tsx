import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/shared/components/mode-toggle", () => ({
  ModeToggle: () => <div data-testid="mode-toggle" />,
}))

import { Topbar } from "@/shared/layout/Topbar"

describe("Topbar", () => {
  it("renders the application title", () => {
    render(<Topbar />)
    expect(screen.getByText("All-in-One ARR")).toBeInTheDocument()
  })

  it("renders the theme toggle", () => {
    render(<Topbar />)
    expect(screen.getByTestId("mode-toggle")).toBeInTheDocument()
  })

  it("no longer renders the dry-run or sync controls", () => {
    render(<Topbar />)
    expect(screen.queryByText("DRY_RUN ON")).not.toBeInTheDocument()
    expect(screen.queryByText("LIVE")).not.toBeInTheDocument()
    expect(screen.queryByRole("switch")).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /sync now/i }),
    ).not.toBeInTheDocument()
  })
})
