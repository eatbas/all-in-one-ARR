import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

const { setTheme, resolvedTheme } = vi.hoisted(() => ({
  setTheme: vi.fn(),
  resolvedTheme: { value: "dark" as "dark" | "light" },
}))

vi.mock("@/shared/components/theme-context", () => ({
  useTheme: () => ({
    theme: resolvedTheme.value,
    resolvedTheme: resolvedTheme.value,
    setTheme,
  }),
}))

import { ModeToggle } from "@/shared/components/mode-toggle"

describe("ModeToggle", () => {
  it("switches from dark to light when clicked", async () => {
    const user = userEvent.setup()
    resolvedTheme.value = "dark"
    setTheme.mockClear()
    render(<ModeToggle />)

    await user.click(screen.getByRole("button", { name: /toggle theme/i }))
    expect(setTheme).toHaveBeenCalledWith("light")
  })

  it("switches from light to dark when clicked", async () => {
    const user = userEvent.setup()
    resolvedTheme.value = "light"
    setTheme.mockClear()
    render(<ModeToggle />)

    await user.click(screen.getByRole("button", { name: /toggle theme/i }))
    expect(setTheme).toHaveBeenCalledWith("dark")
  })
})
