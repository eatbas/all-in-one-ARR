import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/shared/layout/Topbar", () => ({
  Topbar: () => <div data-testid="topbar" />,
}))

import { AppShell } from "@/shared/layout/AppShell"

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<div>dashboard-page</div>} />
          <Route
            path="/list-syncarr"
            element={<div>list-syncarr-page</div>}
          />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe("AppShell", () => {
  it("marks the dashboard link active and renders the routed outlet", () => {
    renderAt("/")

    expect(screen.getByText("dashboard-page")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /dashboard/i })).toHaveAttribute(
      "aria-current",
      "page",
    )
    expect(
      screen.getByRole("link", { name: /list-syncarr/i }),
    ).not.toHaveAttribute("aria-current", "page")
  })

  it("marks the List-Syncarr link active on its route", () => {
    renderAt("/list-syncarr")

    expect(screen.getByText("list-syncarr-page")).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: /list-syncarr/i }),
    ).toHaveAttribute("aria-current", "page")
  })
})
