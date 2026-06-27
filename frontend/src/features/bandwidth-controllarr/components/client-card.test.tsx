import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ClientCard } from "@/features/bandwidth-controllarr/components/client-card"

describe("ClientCard", () => {
  it("renders online stats for qBittorrent", () => {
    render(
      <ClientCard
        label="qBittorrent"
        online={true}
        speed={12.34}
        active={2}
        queue={1}
      />,
    )
    expect(screen.getByText("qBittorrent")).toBeInTheDocument()
    expect(screen.getByText("Online")).toBeInTheDocument()
    expect(screen.getByText("12.34 MB/s")).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
    expect(screen.getByText("1")).toBeInTheDocument()
    expect(screen.queryByText("PAUSED")).not.toBeInTheDocument()
  })

  it("renders the paused badge for SABnzbd", () => {
    render(
      <ClientCard
        label="SABnzbd"
        online={true}
        speed={0}
        active={0}
        queue={0}
        paused={true}
      />,
    )
    expect(screen.getByText("PAUSED")).toBeInTheDocument()
  })

  it("renders the resumed badge for SABnzbd", () => {
    render(
      <ClientCard
        label="SABnzbd"
        online={true}
        speed={0}
        active={0}
        queue={0}
        paused={false}
      />,
    )
    expect(screen.getByText("RESUMED")).toBeInTheDocument()
  })

  it("renders offline state with dimmed stats", () => {
    render(
      <ClientCard
        label="qBittorrent"
        online={false}
        speed={0}
        active={0}
        queue={0}
      />,
    )
    expect(screen.getByText("Offline")).toHaveClass(
      "bg-red-100",
      "text-red-700",
      "dark:bg-red-900/30",
      "dark:text-red-400",
    )
    expect(screen.getByText("0.00 MB/s")).toBeInTheDocument()
  })
})
