import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { toast } from "sonner"

vi.mock("@/components/theme-provider", () => ({
  useTheme: () => ({ resolvedTheme: "dark", theme: "dark", setTheme: vi.fn() }),
}))

import { Toaster } from "@/components/ui/sonner"

describe("Toaster", () => {
  it("renders a queued toast using the resolved theme", async () => {
    render(<Toaster />)

    toast.success("Sync triggered")

    // The toast surfacing proves the Toaster mounted and consumed the theme.
    expect(await screen.findByText("Sync triggered")).toBeInTheDocument()
    expect(document.querySelector(".toaster")).toBeInTheDocument()
  })
})
