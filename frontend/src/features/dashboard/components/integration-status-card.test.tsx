import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { IntegrationStatusCard } from "@/features/dashboard/components/integration-status-card"

const sampleStatus = {
  ok: true,
  detail: "Connected as erena",
  checked_at: "2026-06-23T13:22:46Z",
}

describe("IntegrationStatusCard", () => {
  it("renders an online card with the detail as a tooltip, not visible text", () => {
    render(<IntegrationStatusCard label="Trakt" status={sampleStatus} />)

    expect(screen.getByText("Trakt")).toBeInTheDocument()
    expect(screen.getByLabelText("Online")).toBeInTheDocument()
    expect(screen.getByTitle("Connected as erena")).toHaveAttribute(
      "data-slot",
      "card",
    )
    expect(screen.queryByText("Connected as erena")).not.toBeInTheDocument()
  })

  it("renders an offline card with the failure reason as a tooltip", () => {
    render(
      <IntegrationStatusCard
        label="Seer"
        status={{
          ok: false,
          detail: "Connection refused",
          checked_at: sampleStatus.checked_at,
        }}
      />,
    )

    expect(screen.getByText("Seer")).toBeInTheDocument()
    expect(screen.getByLabelText("Offline")).toBeInTheDocument()
    expect(screen.getByTitle("Connection refused")).toHaveAttribute(
      "data-slot",
      "card",
    )
  })

  it("renders a not-yet-checked state when status is missing", () => {
    render(<IntegrationStatusCard label="Sonarr" status={undefined} />)

    expect(screen.getByText("Sonarr")).toBeInTheDocument()
    expect(screen.getByLabelText("Offline")).toBeInTheDocument()
    expect(screen.getByTitle("Not checked yet")).toHaveAttribute(
      "data-slot",
      "card",
    )
  })

  it("renders the status pill and link pill side by side on the title row", () => {
    render(
      <IntegrationStatusCard
        label="Seer"
        status={sampleStatus}
        url="http://seer.example.com:5055"
      />,
    )

    const link = screen.getByRole("link", { name: /Open Seer/ })
    expect(link).toHaveAttribute("href", "http://seer.example.com:5055")
    expect(link).toHaveAttribute("target", "_blank")
    expect(
      screen.getByText("Seer", { selector: "[data-slot='card-title']" }),
    ).toBeInTheDocument()
    // Both pills share the same pill group next to the title.
    const statusPill = screen.getByLabelText("Online")
    expect(statusPill.parentElement).toBe(link.parentElement)
  })

  it("renders the status pill alone when no URL is provided", () => {
    render(<IntegrationStatusCard label="TMDB" status={sampleStatus} />)

    expect(
      screen.queryByRole("link", { name: /Open TMDB/ }),
    ).not.toBeInTheDocument()
    expect(screen.getByLabelText("Online")).toBeInTheDocument()
  })
})
