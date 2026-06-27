import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ConnectionBadge } from "@/shared/components/connection-badge"

describe("ConnectionBadge", () => {
  it("renders 'Connected' with emerald styling", () => {
    render(<ConnectionBadge state="connected" />)
    const badge = screen.getByText("Connected")
    expect(badge).toHaveClass("border-emerald-500/40")
    expect(badge).toHaveClass("text-emerald-600")
  })

  it("renders 'Offline' with red styling", () => {
    render(<ConnectionBadge state="offline" />)
    const badge = screen.getByText("Offline")
    expect(badge).toHaveClass("border-red-500/40")
    expect(badge).toHaveClass("text-red-600")
  })

  it("renders 'Set key' with amber styling", () => {
    render(<ConnectionBadge state="not-set" />)
    const badge = screen.getByText("Set key")
    expect(badge).toHaveClass("border-amber-500/40")
    expect(badge).toHaveClass("text-amber-600")
  })

  it("renders 'Checking…' with muted slate styling", () => {
    render(<ConnectionBadge state="checking" />)
    const badge = screen.getByText("Checking…")
    expect(badge).toHaveClass("border-slate-500/40")
    expect(badge).toHaveClass("text-slate-600")
  })

  it("surfaces the detail as a hover title", () => {
    render(<ConnectionBadge state="offline" detail="Connection refused" />)
    expect(screen.getByText("Offline")).toHaveAttribute(
      "title",
      "Connection refused",
    )
  })

  it("allows per-state label overrides without changing colours", () => {
    render(
      <ConnectionBadge
        state="not-set"
        labels={{ "not-set": "Not connected" }}
      />,
    )
    const badge = screen.getByText("Not connected")
    expect(badge).toHaveClass("border-amber-500/40")
    expect(badge).toHaveClass("text-amber-600")
  })

  it("merges an external className with the state styling", () => {
    render(<ConnectionBadge state="connected" className="ml-2 uppercase" />)
    const badge = screen.getByText("Connected")
    expect(badge).toHaveClass("border-emerald-500/40")
    expect(badge).toHaveClass("ml-2")
    expect(badge).toHaveClass("uppercase")
  })
})
