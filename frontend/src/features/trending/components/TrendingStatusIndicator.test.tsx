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
    anilist: null,
    poster_url: null,
    seer_status: null,
    imdb_rating: null,
    already_tracked: false,
    in_library: false,
    in_library_available: false,
    ...over,
  }
}

describe("TrendingStatusIndicator", () => {
  it("shows a green tick labelled Available for a downloaded title", () => {
    render(
      <TrendingStatusIndicator
        item={item({ in_library: true, in_library_available: true })}
      />,
    )
    expect(screen.getByLabelText("Available")).toHaveClass(
      "ring-emerald-500",
      "ring-inset",
    )
  })

  it("shows a green tick labelled Available for a Seer-available title", () => {
    render(<TrendingStatusIndicator item={item({ seer_status: 5 })} />)
    expect(screen.getByLabelText("Available")).toHaveClass(
      "ring-emerald-500",
      "ring-inset",
    )
  })

  it.each([
    [2, "Requested"],
    [3, "Processing"],
    [4, "Partial"],
  ])("shows an amber clock circle for Seer status %i (%s)", (status, label) => {
    render(<TrendingStatusIndicator item={item({ seer_status: status })} />)
    // The precise Seer status stays in the aria-label/title; the visible chip
    // reads "Pending" for every in-progress state.
    const indicator = screen.getByLabelText(label)
    expect(indicator).toHaveClass("ring-amber-500")
    expect(indicator).toHaveClass("ring-inset")
    expect(indicator.querySelector("[data-pill-icon-slot]")).toBeInTheDocument()
    expect(indicator.querySelector("svg")).toBeInTheDocument()
    expect(screen.getByText("Pending")).toBeInTheDocument()
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
    expect(screen.getByText("Pending")).toBeInTheDocument()
  })

  it.each([
    [5, "h-8", "size-8", "size-4"],
    [6, "h-7", "size-7", "size-3.5"],
    [7, "h-6", "size-6", "size-3"],
    [8, "h-[22px]", "size-[22px]", "size-3"],
    [9, "h-5", "size-5", "size-[11px]"],
    [10, "h-[18px]", "size-[18px]", "size-2.5"],
    [11, "h-4", "size-4", "size-2"],
  ] as const)(
    "centres both status icons within the shared slot at density %i",
    (density, shellHeight, slotSize, iconSize) => {
      const { rerender } = render(
        <TrendingStatusIndicator
          item={item({ seer_status: 5 })}
          density={density}
        />,
      )

      const available = screen.getByLabelText("Available")
      const availableSlot = available.querySelector("[data-pill-icon-slot]")
      const availableIcon = available.querySelector("svg")
      expect(available).toHaveClass(shellHeight, "rounded-full")
      expect(availableSlot).toHaveClass(
        slotSize,
        "inline-grid",
        "shrink-0",
        "place-items-center",
      )
      // The check stroke sits high in its viewBox, so it takes a small downward
      // nudge; the clock is already concentric and takes none.
      expect(availableIcon).toHaveClass(iconSize, "block", "translate-y-[4%]")

      rerender(
        <TrendingStatusIndicator
          item={item({ seer_status: 3 })}
          density={density}
        />,
      )

      const pending = screen.getByLabelText("Processing")
      const pendingSlot = pending.querySelector("[data-pill-icon-slot]")
      const pendingIcon = pending.querySelector("svg")
      expect(pending).toHaveClass(shellHeight, "rounded-full")
      expect(pendingSlot).toHaveClass(
        slotSize,
        "inline-grid",
        "shrink-0",
        "place-items-center",
      )
      expect(pendingIcon).toHaveClass(iconSize, "block")
      expect(pendingIcon).not.toHaveClass("translate-y-[4%]")
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

      const label = screen.getByText("Pending")
      expect(label).toHaveClass(revealCap)
      expect(label).toHaveClass(outerPadding)
    },
  )

  it("uses full words at low density and prefixes on dense grids", () => {
    const { rerender } = render(
      <TrendingStatusIndicator item={item({ seer_status: 5 })} density={5} />,
    )
    expect(screen.getByText("Available")).toBeInTheDocument()
    rerender(
      <TrendingStatusIndicator item={item({ seer_status: 5 })} density={9} />,
    )
    expect(screen.getByText("Ava.")).toBeInTheDocument()

    rerender(
      <TrendingStatusIndicator item={item({ seer_status: 3 })} density={5} />,
    )
    expect(screen.getByText("Pending")).toBeInTheDocument()
    rerender(
      <TrendingStatusIndicator item={item({ seer_status: 3 })} density={11} />,
    )
    expect(screen.getByText("Pend.")).toBeInTheDocument()
  })

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
