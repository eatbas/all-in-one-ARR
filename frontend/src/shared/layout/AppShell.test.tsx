import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/layout/Topbar", () => ({
  Topbar: () => <div data-testid="topbar" />,
}))

import { AppShell } from "@/shared/layout/AppShell"
import { SIDEBAR_COLLAPSED_STORAGE_KEY } from "@/shared/layout/sidebar-state"
import { APP_VERSION } from "@/shared/lib/version"

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<div>dashboard-page</div>} />
          <Route path="/list-syncarr" element={<div>list-syncarr-page</div>} />
          <Route path="/deletarr" element={<div>deletarr-page</div>} />
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

  it("shows the app version pinned in the sidebar footer", () => {
    renderAt("/")

    expect(screen.getByText(`v${APP_VERSION}`)).toBeInTheDocument()
  })

  it("keeps the chrome static inside a fixed-height shell with <main> as the only scroller", () => {
    const { container } = renderAt("/")

    // App-shell scroll model: the shell owns the viewport and only <main>
    // scrolls, so no overlay scroll lock can ever move the sidebar or topbar.
    // jsdom applies no layout, so this asserts the class contract instead.
    const shell = container.firstElementChild
    expect(shell).toHaveClass("h-dvh", "overflow-hidden")
    const sidebar = container.querySelector("#primary-sidebar")
    expect(sidebar).not.toBeNull()
    expect(sidebar).toHaveClass("h-full")
    expect(sidebar).not.toHaveClass("sticky")
    const main = container.querySelector("main")
    expect(main).toHaveClass("overflow-y-auto")
  })

  it("focuses the scroll pane on load and navigation so keyboard scrolling works", async () => {
    const user = userEvent.setup()
    const { container } = renderAt("/")

    // The document never scrolls, so PageDown/Space/arrows only work while
    // focus sits inside <main>. The shell focuses the pane programmatically
    // on load and on every route change; tabIndex=-1 keeps it out of the Tab
    // order.
    const main = container.querySelector("main")
    expect(main).toHaveAttribute("tabindex", "-1")
    expect(main).toHaveFocus()

    await user.click(screen.getByRole("link", { name: /list-syncarr/i }))

    expect(screen.getByText("list-syncarr-page")).toBeInTheDocument()
    expect(main).toHaveFocus()
  })

  it("marks the List-Syncarr link active on its route", () => {
    renderAt("/list-syncarr")

    expect(screen.getByText("list-syncarr-page")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /list-syncarr/i })).toHaveAttribute(
      "aria-current",
      "page",
    )
  })

  it("marks the Deletarr link active on its route", () => {
    renderAt("/deletarr")

    expect(screen.getByText("deletarr-page")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /deletarr/i })).toHaveAttribute(
      "aria-current",
      "page",
    )
  })

  it("collapses the sidebar to a rail and persists the choice", async () => {
    const user = userEvent.setup()
    renderAt("/")

    const collapse = screen.getByRole("button", { name: /collapse sidebar/i })
    expect(collapse).toHaveAttribute("aria-expanded", "true")
    // The toggle is wired to the region it shows/hides for assistive tech.
    expect(collapse).toHaveAttribute("aria-controls", "primary-sidebar")

    await user.click(collapse)

    const expand = screen.getByRole("button", { name: /expand sidebar/i })
    expect(expand).toHaveAttribute("aria-expanded", "false")
    expect(localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY)).toBe("true")
    // The version stays pinned in the footer even when collapsed to the rail.
    expect(screen.getByText(`v${APP_VERSION}`)).toBeInTheDocument()
    // Labels are visually hidden but remain in the a11y tree, so links keep
    // their accessible names while collapsed.
    expect(screen.getByRole("link", { name: /dashboard/i })).toBeInTheDocument()
  })

  it("restores the collapsed state from localStorage", () => {
    localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, "true")
    renderAt("/")

    expect(
      screen.getByRole("button", { name: /expand sidebar/i }),
    ).toHaveAttribute("aria-expanded", "false")
    expect(screen.getByRole("link", { name: /dashboard/i })).toBeInTheDocument()
  })

  it("stays usable when localStorage is unavailable", async () => {
    vi.stubGlobal("localStorage", undefined)
    const user = userEvent.setup()
    renderAt("/")

    const collapse = screen.getByRole("button", { name: /collapse sidebar/i })
    await user.click(collapse)

    expect(
      screen.getByRole("button", { name: /expand sidebar/i }),
    ).toBeInTheDocument()
  })
})
