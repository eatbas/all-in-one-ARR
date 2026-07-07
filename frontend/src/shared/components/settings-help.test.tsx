import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { describe, expect, it } from "vitest"

import { SettingsHelp } from "@/shared/components/settings-help"
import { TooltipProvider } from "@/shared/components/ui/tooltip"

function renderWithTooltip(ui: ReactElement) {
  return render(<TooltipProvider>{ui}</TooltipProvider>)
}

describe("SettingsHelp", () => {
  it("renders an accessible icon button", () => {
    renderWithTooltip(
      <SettingsHelp label="Status check interval">
        How often status checks run.
      </SettingsHelp>,
    )

    expect(
      screen.getByRole("button", { name: "Explain Status check interval" }),
    ).toBeInTheDocument()
  })

  it("shows the explanation on hover", async () => {
    const user = userEvent.setup()
    renderWithTooltip(
      <SettingsHelp label="API key">
        The key is saved server-side and never shown again.
      </SettingsHelp>,
    )

    await user.hover(screen.getByRole("button", { name: "Explain API key" }))

    expect(
      (
        await screen.findAllByText(
          "The key is saved server-side and never shown again.",
        )
      ).length,
    ).toBeGreaterThan(0)
  })

  it("shows the explanation on keyboard focus", async () => {
    const user = userEvent.setup()
    renderWithTooltip(
      <SettingsHelp label="Sync interval">
        How often the sync loop runs.
      </SettingsHelp>,
    )

    await user.tab()

    expect(
      screen.getByRole("button", { name: "Explain Sync interval" }),
    ).toHaveFocus()
    expect(
      (await screen.findAllByText("How often the sync loop runs.")).length,
    ).toBeGreaterThan(0)
  })
})
