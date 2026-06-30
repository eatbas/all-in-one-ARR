import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useDeletarrSettings: vi.fn(),
  useUpdateDeletarrSettings: vi.fn(),
}))

import type { DeletarrSettings } from "@/shared/lib/api"
import { useDeletarrSettings, useUpdateDeletarrSettings } from "@/shared/lib/queries"
import { mutationResult, queryResult } from "@/shared/test/mock-query"

import { Settings } from "./Settings"

const SETTINGS: DeletarrSettings = {
  movies_path: "/media/movies",
  tv_path: "/media/tv",
}

beforeEach(() => {
  vi.mocked(useDeletarrSettings).mockReturnValue(queryResult(SETTINGS))
  vi.mocked(useUpdateDeletarrSettings).mockReturnValue(mutationResult(vi.fn(), false))
})

describe("Deletarr Settings", () => {
  it("renders Movies path and TV path from useDeletarrSettings", () => {
    render(<Settings />)

    expect(screen.getByLabelText("Movies path")).toHaveValue("/media/movies")
    expect(screen.getByLabelText("TV path")).toHaveValue("/media/tv")
  })

  it("saves only a changed Movies path", async () => {
    const user = userEvent.setup()
    const mutate = vi.fn()
    vi.mocked(useUpdateDeletarrSettings).mockReturnValue(
      mutationResult(mutate, false),
    )
    render(<Settings />)

    await user.clear(screen.getByLabelText("Movies path"))
    await user.type(screen.getByLabelText("Movies path"), "/srv/movies")
    await user.click(screen.getByRole("button", { name: "Save" }))

    expect(mutate).toHaveBeenCalledWith({ movies_path: "/srv/movies" })
  })

  it("saves only a changed TV path", async () => {
    const user = userEvent.setup()
    const mutate = vi.fn()
    vi.mocked(useUpdateDeletarrSettings).mockReturnValue(
      mutationResult(mutate, false),
    )
    render(<Settings />)

    await user.clear(screen.getByLabelText("TV path"))
    await user.type(screen.getByLabelText("TV path"), "/srv/tv")
    await user.click(screen.getByRole("button", { name: "Save" }))

    expect(mutate).toHaveBeenCalledWith({ tv_path: "/srv/tv" })
  })

  it("saves both paths when both change", async () => {
    const user = userEvent.setup()
    const mutate = vi.fn()
    vi.mocked(useUpdateDeletarrSettings).mockReturnValue(
      mutationResult(mutate, false),
    )
    render(<Settings />)

    await user.clear(screen.getByLabelText("Movies path"))
    await user.type(screen.getByLabelText("Movies path"), "/srv/movies")
    await user.clear(screen.getByLabelText("TV path"))
    await user.type(screen.getByLabelText("TV path"), "/srv/tv")
    await user.click(screen.getByRole("button", { name: "Save" }))

    expect(mutate).toHaveBeenCalledWith({
      movies_path: "/srv/movies",
      tv_path: "/srv/tv",
    })
  })

  it("does not submit unchanged drafts", async () => {
    const user = userEvent.setup()
    const mutate = vi.fn()
    vi.mocked(useUpdateDeletarrSettings).mockReturnValue(
      mutationResult(mutate, false),
    )
    render(<Settings />)

    await user.click(screen.getByRole("button", { name: "Save" }))

    expect(mutate).not.toHaveBeenCalled()
  })

  it("does not submit blank-only drafts", async () => {
    const user = userEvent.setup()
    const mutate = vi.fn()
    vi.mocked(useUpdateDeletarrSettings).mockReturnValue(
      mutationResult(mutate, false),
    )
    render(<Settings />)

    await user.clear(screen.getByLabelText("Movies path"))
    await user.type(screen.getByLabelText("Movies path"), "   ")
    await user.click(screen.getByRole("button", { name: "Save" }))

    expect(mutate).not.toHaveBeenCalled()
  })

  it("disables save controls while the mutation is pending", () => {
    const mutate = vi.fn()
    vi.mocked(useUpdateDeletarrSettings).mockReturnValue(
      mutationResult(mutate, true),
    )
    render(<Settings />)

    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled()
    expect(screen.getByLabelText("Movies path")).toBeDisabled()
    expect(screen.getByLabelText("TV path")).toBeDisabled()
  })

  it("shows a loading state while settings are loading", () => {
    vi.mocked(useDeletarrSettings).mockReturnValue(
      queryResult<DeletarrSettings>(undefined, true),
    )

    render(<Settings />)

    expect(screen.getByText("Loading Deletarr settings…")).toBeInTheDocument()
  })
})
