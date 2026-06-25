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

  it("renders no toggle or sync controls", () => {
    render(<Topbar />)
    expect(screen.queryByRole("switch")).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /sync now/i }),
    ).not.toBeInTheDocument()
  })
})
