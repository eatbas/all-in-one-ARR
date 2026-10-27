import { render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { DashboardSource } from "@/shared/lib/api"
import { SourceCard } from "@/features/dashboard/components/source-card"

const NOW = new Date("2026-10-27T12:00:00Z")

function source(overrides: Partial<DashboardSource>): DashboardSource {
  return {
    key: "seer",
    label: "Seer",
    state: "ok",
    detail: null,
    stale_since: null,
    updated_at: null,
    link: "/settings",
    metrics: [],
    ...overrides,
  }
}

const SEER_METRICS: DashboardSource["metrics"] = [
  { key: "seer.requests_total", label: "Requests", unit: "count", value: 1284 },
  {
    key: "seer.requests_pending",
    label: "Pending",
    unit: "count",
    value: null,
  },
]

function renderCard(value: DashboardSource) {
  return render(
    <MemoryRouter>
      <SourceCard source={value} />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] })
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

describe("SourceCard", () => {
  it("links the title to the source page and lists metrics without a badge", () => {
    const { container } = renderCard(
      source({
        key: "findarr",
        label: "Findarr",
        link: "/findarr",
        metrics: SEER_METRICS,
      }),
    )

    expect(screen.getByRole("link", { name: "Findarr" })).toHaveAttribute(
      "href",
      "/findarr",
    )
    expect(container.querySelector("[data-slot='badge']")).toBeNull()
    const list = screen.getByText("Requests").closest("dl")!
    expect(within(list).getByText("Requests")).toBeInTheDocument()
    expect(within(list).getByText((1284).toLocaleString())).toBeInTheDocument()
    expect(within(list).getByText("—")).toBeInTheDocument()
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("shows an offline badge, the stale time and detail with snapshot values", () => {
    renderCard(
      source({
        state: "offline",
        detail: "Seer connection failed: timed out",
        stale_since: "2026-10-26T22:00:00Z",
        metrics: SEER_METRICS,
      }),
    )

    expect(screen.getByText("Offline")).toHaveAttribute(
      "data-variant",
      "destructive",
    )
    expect(screen.getByText("Stale since 14 hours ago")).toBeInTheDocument()
    expect(
      screen.getByText("Seer connection failed: timed out"),
    ).toBeInTheDocument()
    expect(screen.getByText("Requests")).toBeInTheDocument()
  })

  it("says when an offline source has no earlier snapshot", () => {
    renderCard(source({ state: "offline" }))

    expect(screen.getByText("No earlier snapshot")).toBeInTheDocument()
    expect(screen.queryByText("·")).not.toBeInTheDocument()
  })

  it("links a not-configured source to Settings", () => {
    renderCard(
      source({
        key: "list_syncarr",
        label: "List-Syncarr",
        link: "/list-syncarr",
        state: "not_configured",
        detail: "No Trakt lists are tracked yet.",
      }),
    )

    expect(screen.getByText("Not configured")).toHaveAttribute(
      "data-variant",
      "outline",
    )
    expect(
      screen.getByText("No Trakt lists are tracked yet.", { exact: false }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: "Set up in Settings" }),
    ).toHaveAttribute("href", "/settings")
    expect(screen.getByRole("link", { name: "List-Syncarr" })).toHaveAttribute(
      "href",
      "/list-syncarr",
    )
  })

  it("falls back to a generic not-configured line", () => {
    renderCard(source({ state: "not_configured" }))

    expect(
      screen.getByText("This service is not connected yet.", { exact: false }),
    ).toBeInTheDocument()
  })

  it("mutes a disabled source and explains why it has no figures", () => {
    const { container } = renderCard(
      source({
        key: "bandwidth",
        label: "Bandwidth-Controllarr",
        link: "/bandwidth-controllarr",
        state: "disabled",
      }),
    )

    expect(screen.getByText("Disabled")).toHaveAttribute(
      "data-variant",
      "secondary",
    )
    expect(container.querySelector("[data-slot='card']")).toHaveClass(
      "bg-muted/50",
    )
    expect(
      screen.getByText("No statistics while the module is disabled."),
    ).toBeInTheDocument()
  })

  it("still lists the figures a disabled source reports", () => {
    renderCard(source({ state: "disabled", metrics: SEER_METRICS }))

    expect(screen.getByText("Requests")).toBeInTheDocument()
    expect(
      screen.queryByText("No statistics while the module is disabled."),
    ).not.toBeInTheDocument()
  })

  it("shows when a source without figures last refreshed", () => {
    const { unmount } = renderCard(
      source({
        key: "trending",
        label: "Trending",
        link: "/trending",
        updated_at: "2026-10-27T10:00:00Z",
      }),
    )
    expect(screen.getByText("Last refreshed 2 hours ago")).toBeInTheDocument()
    unmount()

    renderCard(source({ key: "trending", label: "Trending" }))
    expect(screen.getByText("Not refreshed yet")).toBeInTheDocument()
  })

  it("shows a source's detail line", () => {
    renderCard(
      source({
        key: "bandwidth",
        label: "Bandwidth-Controllarr",
        detail: "SABnzbd is downloading.",
      }),
    )

    expect(screen.getByText("SABnzbd is downloading.")).toBeInTheDocument()
  })
})
