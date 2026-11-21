import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useRemindarrBadgeCount: vi.fn(),
}))

import { NavBadge } from "@/shared/layout/nav-badge"
import { useRemindarrBadgeCount } from "@/shared/lib/queries"

beforeEach(() => {
  vi.mocked(useRemindarrBadgeCount).mockReturnValue(14)
})

describe("NavBadge", () => {
  it("shows the count as a pill after the label when expanded", () => {
    render(<NavBadge source="remindarr" collapsed={false} />)
    const badge = screen.getByLabelText("14 unwatched episodes")
    expect(badge).toHaveTextContent("14")
    expect(badge).toHaveAttribute("title", "14 unwatched episodes")
    expect(badge).toHaveClass("ml-auto")
    expect(badge).not.toHaveClass("absolute")
  })

  it("shows a small count over the icon when collapsed", () => {
    render(<NavBadge source="remindarr" collapsed />)
    const badge = screen.getByLabelText("14 unwatched episodes")
    expect(badge).toHaveClass("absolute", "rounded-full")
    expect(badge).not.toHaveClass("ml-auto")
  })

  it("uses the singular label for one episode", () => {
    vi.mocked(useRemindarrBadgeCount).mockReturnValue(1)
    render(<NavBadge source="remindarr" collapsed={false} />)
    expect(screen.getByLabelText("1 unwatched episode")).toHaveTextContent("1")
  })

  it("renders nothing without a count", () => {
    vi.mocked(useRemindarrBadgeCount).mockReturnValue(null)
    const { container } = render(
      <NavBadge source="remindarr" collapsed={false} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
