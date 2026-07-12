import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { ClientCard } from "@/features/bandwidth-controllarr/components/client-card"

describe("ClientCard", () => {
  it("renders online stats for qBittorrent", () => {
    render(
      <ClientCard
        label="qBittorrent"
        client="qbittorrent"
        online={true}
        speed={12.34}
        active={2}
        queue={1}
        manuallyPaused={false}
        controlPending={false}
        onManualPausedChange={vi.fn()}
      />,
    )
    expect(screen.getByText("qBittorrent")).toBeInTheDocument()
    expect(screen.getByText("Online")).toBeInTheDocument()
    expect(screen.getByText("12.34 MB/s")).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
    expect(screen.getByText("1")).toBeInTheDocument()
    expect(screen.queryByText("PAUSED")).not.toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Pause qBittorrent downloads" }),
    ).toBeEnabled()
  })

  it("renders the paused badge for SABnzbd", () => {
    render(
      <ClientCard
        label="SABnzbd"
        client="sabnzbd"
        online={true}
        speed={0}
        active={0}
        queue={0}
        paused={true}
        manuallyPaused={true}
        controlPending={false}
        onManualPausedChange={vi.fn()}
      />,
    )
    expect(screen.getByText("PAUSED")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Resume SABnzbd downloads" }),
    ).toBeEnabled()
  })

  it("renders the resumed badge for SABnzbd", () => {
    render(
      <ClientCard
        label="SABnzbd"
        client="sabnzbd"
        online={true}
        speed={0}
        active={0}
        queue={0}
        paused={false}
        manuallyPaused={false}
        controlPending={false}
        onManualPausedChange={vi.fn()}
      />,
    )
    expect(screen.getByText("RESUMED")).toBeInTheDocument()
  })

  it("omits the actual-state badge when the client does not report it", () => {
    render(
      <ClientCard
        label="qBittorrent"
        client="qbittorrent"
        online={true}
        speed={0}
        active={0}
        queue={0}
        paused={null}
        manuallyPaused={false}
        controlPending={false}
        onManualPausedChange={vi.fn()}
      />,
    )

    expect(screen.queryByText("PAUSED")).not.toBeInTheDocument()
    expect(screen.queryByText("RESUMED")).not.toBeInTheDocument()
  })

  it("renders offline state with dimmed stats", () => {
    render(
      <ClientCard
        label="qBittorrent"
        client="qbittorrent"
        online={false}
        speed={0}
        active={0}
        queue={0}
        manuallyPaused={false}
        controlPending={false}
        onManualPausedChange={vi.fn()}
      />,
    )
    expect(screen.getByText("Offline")).toHaveClass(
      "bg-red-100",
      "text-red-700",
      "dark:bg-red-900/30",
      "dark:text-red-400",
    )
    expect(screen.getByText("0.00 MB/s")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Pause qBittorrent downloads" }),
    ).toBeDisabled()
  })

  it("requests the opposite manual pause state", async () => {
    const user = userEvent.setup()
    const onManualPausedChange = vi.fn()
    render(
      <ClientCard
        label="qBittorrent"
        client="qbittorrent"
        online={true}
        speed={0}
        active={0}
        queue={0}
        manuallyPaused={false}
        controlPending={false}
        onManualPausedChange={onManualPausedChange}
      />,
    )

    await user.click(
      screen.getByRole("button", { name: "Pause qBittorrent downloads" }),
    )
    expect(onManualPausedChange).toHaveBeenCalledWith(true)
  })

  it("disables manual control while a command is pending", () => {
    render(
      <ClientCard
        label="SABnzbd"
        client="sabnzbd"
        online={true}
        speed={0}
        active={0}
        queue={0}
        manuallyPaused={false}
        controlPending={true}
        onManualPausedChange={vi.fn()}
      />,
    )

    expect(
      screen.getByRole("button", { name: "Pause SABnzbd downloads" }),
    ).toBeDisabled()
  })
})
