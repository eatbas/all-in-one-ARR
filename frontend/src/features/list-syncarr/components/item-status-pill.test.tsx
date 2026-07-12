import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ItemStatusPill } from "@/features/list-syncarr/components/item-status-pill"

describe("ItemStatusPill", () => {
  it("shows a green tick labelled Available for an available item", () => {
    render(<ItemStatusPill status="available" density={8} />)
    const pill = screen.getByLabelText("Available")
    expect(pill).toHaveClass("ring-emerald-500", "ring-inset")
    expect(pill.querySelector("[data-pill-icon-slot]")).toBeInTheDocument()
    expect(pill.querySelector("svg")).toBeInTheDocument()
  })

  it("shows an amber clock revealing Pending for a requested item", () => {
    render(<ItemStatusPill status="requested" density={8} />)
    // The precise word stays in the aria-label/title; the visible hover label
    // reads "Pending", matching the Trending cards.
    const pill = screen.getByLabelText("Requested")
    expect(pill).toHaveClass("ring-amber-500", "ring-inset")
    expect(screen.getByText("Pending")).toBeInTheDocument()
  })

  it("shows a sky pill labelled Synced for a synced item", () => {
    render(<ItemStatusPill status="synced" density={8} />)
    const pill = screen.getByLabelText("Synced from Trakt")
    expect(pill).toHaveClass("ring-sky-500", "ring-inset")
    expect(screen.getByText("Synced")).toBeInTheDocument()
  })

  it("shows a muted pill labelled Removed for a removed item", () => {
    render(<ItemStatusPill status="removed" density={8} />)
    const pill = screen.getByLabelText("Removed from the list")
    expect(pill).toHaveClass("ring-inset")
    expect(screen.getByText("Removed")).toBeInTheDocument()
  })
})
