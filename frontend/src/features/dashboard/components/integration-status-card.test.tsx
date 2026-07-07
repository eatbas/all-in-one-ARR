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
    expect(screen.getByText("Online")).toBeInTheDocument()
    expect(screen.getByText("Connected as erena")).toBeInTheDocument()
    expect(screen.getByText("trakt")).toBeInTheDocument()
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
    expect(screen.getByText("Offline")).toBeInTheDocument()
    expect(screen.getByText("Connection refused")).toBeInTheDocument()
  })

  it("renders a not-yet-checked state when status is missing", () => {
    render(
      <IntegrationStatusCard name="sonarr" label="Sonarr" status={undefined} />,
    )

    expect(screen.getByText("Sonarr")).toBeInTheDocument()
    expect(screen.getByText("Offline")).toBeInTheDocument()
    expect(screen.getByText("Not checked yet")).toBeInTheDocument()
  })
})
