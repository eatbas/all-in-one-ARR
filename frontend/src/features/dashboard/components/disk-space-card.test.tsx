import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { DiskSpaceCard } from "@/features/dashboard/components/disk-space-card"

const TB = 1024 ** 4

describe("DiskSpaceCard", () => {
  it("shows an empty state when no disks are reported", () => {
    render(<DiskSpaceCard disks={[]} />)

    expect(screen.getByText("Disk space")).toBeInTheDocument()
    expect(screen.getByText("No disk space reported yet.")).toBeInTheDocument()
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument()
  })

  it("renders a used/total bar and free space per disk", () => {
    render(
      <DiskSpaceCard
        disks={[
          {
            app: "sonarr",
            path: "/data/media/tv",
            label: "TV",
            free_bytes: 2.9 * TB,
            total_bytes: 10 * TB,
          },
          {
            app: "radarr",
            path: "/movies",
            label: null,
            free_bytes: 0,
            total_bytes: 0,
          },
        ]}
      />,
    )

    const tv = screen.getByRole("progressbar", { name: "Sonarr TV used" })
    expect(tv).toHaveAttribute("aria-valuenow", "71")
    expect(tv).toHaveAttribute("aria-valuemin", "0")
    expect(tv).toHaveAttribute("aria-valuemax", "100")
    expect(tv.firstElementChild).toHaveStyle({ width: "71%" })
    expect(screen.getByText("2.9 TB free of 10.0 TB")).toBeInTheDocument()
    expect(screen.getByText("/data/media/tv")).toBeInTheDocument()

    // A disk of unknown size reads as 0 % used and is named by its path.
    expect(
      screen.getByRole("progressbar", { name: "Radarr /movies used" }),
    ).toHaveAttribute("aria-valuenow", "0")
    expect(screen.getByText("0 B free of 0 B")).toBeInTheDocument()
  })
})
