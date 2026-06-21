import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/components/layout/Topbar", () => ({
  Topbar: () => <div data-testid="topbar" />,
}))

import { AppShell } from "@/components/layout/AppShell"

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<div>dashboard-page</div>} />
          <Route path="/items" element={<div>items-page</div>} />
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
      screen.getByRole("link", { name: /items/i }),
    ).not.toHaveAttribute("aria-current", "page")
  })

  it("marks the items link active on the items route", () => {
    renderAt("/items")

    expect(screen.getByText("items-page")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /items/i })).toHaveAttribute(
      "aria-current",
      "page",
    )
  })
})
