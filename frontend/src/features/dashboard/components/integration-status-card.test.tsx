import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { IntegrationStatusCard } from "@/features/dashboard/components/integration-status-card"

const sampleStatus = {
  ok: true,
  detail: "Connected as erena",
  checked_at: "2026-06-23T13:22:46Z",
}

describe("IntegrationStatusCard", () => {
  it("renders an online card for a healthy integration", () => {
    render(
      <IntegrationStatusCard
        name="trakt"
        label="Trakt"
        status={sampleStatus}
      />,
    )

    expect(screen.getByText("Trakt")).toBeInTheDocument()
    expect(screen.getByLabelText("Online")).toBeInTheDocument()
    expect(screen.getByText("Connected as erena")).toBeInTheDocument()
  })

  it("renders an offline card for a failing integration", () => {
    render(
      <IntegrationStatusCard
        name="seer"
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
    expect(screen.getByText("Connection refused")).toBeInTheDocument()
  })

  it("renders a not-yet-checked state when status is missing", () => {
    render(
      <IntegrationStatusCard name="sonarr" label="Sonarr" status={undefined} />,
    )

    expect(screen.getByText("Sonarr")).toBeInTheDocument()
    expect(screen.getByLabelText("Offline")).toBeInTheDocument()
    expect(screen.getByText("Not checked yet")).toBeInTheDocument()
  })

  it("renders a link pill and a status light on the description line when a URL is provided", () => {
    render(
      <IntegrationStatusCard
        name="seer"
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
    expect(screen.getByLabelText("Online")).toBeInTheDocument()
  })

  it("does not render a link pill when no URL is provided", () => {
    render(
      <IntegrationStatusCard name="tmdb" label="TMDB" status={sampleStatus} />,
    )

    expect(
      screen.queryByRole("link", { name: /Open TMDB/ }),
    ).not.toBeInTheDocument()
    expect(screen.getByLabelText("Online")).toBeInTheDocument()
  })
})
