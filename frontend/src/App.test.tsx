import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/lib/queries", () => ({
  useStatus: vi.fn(() => ({ data: undefined })),
  useActivity: vi.fn(() => ({ data: [], isLoading: false })),
  useItems: vi.fn(() => ({ data: [], isLoading: false })),
  useSyncNow: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useSetDryRun: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

import App from "@/App"
import { ThemeProvider } from "@/components/theme-provider"
import { TooltipProvider } from "@/components/ui/tooltip"

function renderAt(path: string) {
  return render(
    <ThemeProvider defaultTheme="dark" storageKey="app-test-theme">
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </TooltipProvider>
    </ThemeProvider>,
  )
}

describe("App routing", () => {
  it("renders the dashboard at /", () => {
    renderAt("/")
    expect(screen.getByText("Recent activity")).toBeInTheDocument()
  })

  it("renders the items page at /items", () => {
    renderAt("/items")
    expect(
      screen.getByText("Every movie and show mirrored from Trakt."),
    ).toBeInTheDocument()
  })

  it("redirects unknown routes back to the dashboard", () => {
    renderAt("/does-not-exist")
    expect(screen.getByText("Recent activity")).toBeInTheDocument()
  })
})
