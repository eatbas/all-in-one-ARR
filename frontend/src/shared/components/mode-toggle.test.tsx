import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

const { setTheme } = vi.hoisted(() => ({ setTheme: vi.fn() }))
vi.mock("@/shared/components/theme-context", () => ({
  useTheme: () => ({ theme: "dark", resolvedTheme: "dark", setTheme }),
}))

import { ModeToggle } from "@/shared/components/mode-toggle"

describe("ModeToggle", () => {
  it("sets the theme for each menu option", async () => {
    const user = userEvent.setup()
    render(<ModeToggle />)

    const options = [
      { label: "Light", value: "light" },
      { label: "Dark", value: "dark" },
      { label: "System", value: "system" },
    ] as const

    for (const { label, value } of options) {
      await user.click(screen.getByRole("button", { name: /toggle theme/i }))
      await user.click(await screen.findByRole("menuitem", { name: label }))
      expect(setTheme).toHaveBeenCalledWith(value)
    }
  })
})
