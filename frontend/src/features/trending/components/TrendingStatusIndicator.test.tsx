import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { TrendingStatusIndicator } from "@/features/trending/components/TrendingStatusIndicator"
import type { TrendingItem } from "@/shared/lib/api"

function item(over: Partial<TrendingItem>): TrendingItem {
  return {
    source: "tmdb",
    media_type: "movie",
    tmdb: 100,
    imdb: null,
    tvdb: null,
    trakt: null,
    slug: null,
    title: "Dune",
    year: 2021,
    seer_status: null,
    already_tracked: false,
    in_library: false,
    in_library_available: false,
    ...over,
  }
}

describe("TrendingStatusIndicator", () => {
  it("shows a green tick labelled In library for a downloaded title", () => {
    render(
      <TrendingStatusIndicator
        item={item({ in_library: true, in_library_available: true })}
      />,
    )
    expect(screen.getByLabelText("In library")).toHaveClass("bg-emerald-500")
  })

  it("shows a green tick labelled Available for a Seer-available title", () => {
    render(<TrendingStatusIndicator item={item({ seer_status: 5 })} />)
    expect(screen.getByLabelText("Available")).toHaveClass("bg-emerald-500")
  })

  it.each([
    [2, "Requested"],
    [3, "Processing"],
    [4, "Partial"],
  ])("shows an amber clock circle for Seer status %i (%s)", (status, label) => {
    render(<TrendingStatusIndicator item={item({ seer_status: status })} />)
    const indicator = screen.getByLabelText(label)
    expect(indicator).toHaveClass("ring-amber-500")
    expect(indicator).toHaveClass("ring-inset")
    expect(indicator.querySelector("[data-pill-icon-slot]")).toBeInTheDocument()
    expect(indicator.querySelector("svg")).toBeInTheDocument()
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it("shows an amber clock circle for a library record without the media", () => {
    render(
      <TrendingStatusIndicator
        item={item({ in_library: true, in_library_available: false })}
      />,
    )
    expect(
      screen.getByLabelText("In library, media not downloaded"),
    ).toHaveClass("ring-inset")
    expect(screen.getByText("In progress")).toBeInTheDocument()
  })

  it.each([
    [5, "size-8", "size-4"],
    [6, "size-7", "size-3.5"],
    [7, "size-6", "size-3"],
  ] as const)(
    "uses the shared shell and icon slot at density %i",
    (density, shellSize, iconSize) => {
      render(
        <TrendingStatusIndicator
          item={item({ seer_status: 3 })}
          density={density}
        />,
      )

      const indicator = screen.getByLabelText("Processing")
      expect(indicator).toHaveClass(shellSize)
      expect(indicator.querySelector("[data-pill-icon-slot]")).toHaveClass(
        shellSize,
      )
      expect(indicator.querySelector("svg")).toHaveClass(iconSize)
    },
  )

  it.each([
    [5, "group-hover/status:max-w-24", "group-hover/status:pr-2"],
    [6, "group-hover/status:max-w-20", "group-hover/status:pr-1.5"],
    [7, "group-hover/status:max-w-20", "group-hover/status:pr-1.5"],
  ] as const)(
    "reveals the label with a wide-enough cap and outer-edge padding at density %i",
    (density, revealCap, outerPadding) => {
      render(
        <TrendingStatusIndicator
          item={item({ seer_status: 3 })}
          density={density}
        />,
      )

      const label = screen.getByText("Processing")
      expect(label).toHaveClass(revealCap)
      expect(label).toHaveClass(outerPadding)
    },
  )

  it("prefers the Seer detail when both pending signals are present", () => {
    render(
      <TrendingStatusIndicator
        item={item({
          in_library: true,
          in_library_available: false,
          seer_status: 3,
        })}
      />,
    )
    expect(screen.getByLabelText("Processing")).toBeInTheDocument()
  })

  it("renders nothing for a plain discovery item", () => {
    const { container } = render(<TrendingStatusIndicator item={item({})} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("renders nothing for an unknown Seer status", () => {
    const { container } = render(
      <TrendingStatusIndicator item={item({ seer_status: 1 })} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
