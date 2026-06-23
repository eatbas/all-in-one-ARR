import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { toast } from "sonner"

vi.mock("@/shared/components/theme-provider", () => ({
  useTheme: () => ({ resolvedTheme: "dark", theme: "dark", setTheme: vi.fn() }),
}))

import { Toaster } from "@/shared/components/ui/sonner"

describe("Toaster", () => {
  it("renders a queued toast bottom-right with a close button", async () => {
    render(<Toaster />)

    toast.success("Sync triggered")

    // The toast surfacing proves the Toaster mounted and consumed the theme.
    expect(await screen.findByText("Sync triggered")).toBeInTheDocument()
    expect(document.querySelector(".toaster")).toBeInTheDocument()

    // The wrapper defaults the position to bottom-right.
    const toaster = document.querySelector("[data-sonner-toaster]")
    expect(toaster).toHaveAttribute("data-y-position", "bottom")
    expect(toaster).toHaveAttribute("data-x-position", "right")

    // The close button (X) is rendered on the toast.
    expect(
      await screen.findByRole("button", { name: /close toast/i }),
    ).toBeInTheDocument()
  })
})
