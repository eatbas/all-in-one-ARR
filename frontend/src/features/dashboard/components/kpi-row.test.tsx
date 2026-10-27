import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { KpiRow } from "@/features/dashboard/components/kpi-row"

describe("KpiRow", () => {
  it("renders eight skeleton tiles while loading", () => {
    render(<KpiRow kpis={undefined} />)

    const region = screen.getByRole("region", { name: "Key figures loading" })
    expect(region).toHaveAttribute("aria-busy", "true")
    expect(region.children).toHaveLength(8)
  })

  it("renders each figure formatted by unit, muting unavailable ones", () => {
    render(
      <KpiRow
        kpis={[
          { key: "movies", label: "Movies", unit: "count", value: 2236 },
          {
            key: "free_disk",
            label: "Free disk space",
            unit: "bytes",
            value: 1024 ** 4,
          },
          {
            key: "pending_requests",
            label: "Pending requests",
            unit: "count",
            value: null,
          },
        ]}
      />,
    )

    const region = screen.getByRole("region", { name: "Key figures" })
    expect(within(region).getByText("Movies")).toBeInTheDocument()
    expect(within(region).getByText((2236).toLocaleString())).not.toHaveClass(
      "text-muted-foreground",
    )
    expect(within(region).getByText("1.0 TB")).toBeInTheDocument()
    expect(within(region).getByText("—")).toHaveClass("text-muted-foreground")
  })
})
