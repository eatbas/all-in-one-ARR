import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/lib/queries", () => ({
  useTraktSettings: vi.fn(),
}))

import { useTraktSettings } from "@/lib/queries"

import { Lists } from "@/pages/Lists"
import { queryResult } from "@/test/mock-query"

const sampleSettings = {
  client_id_hint: "1234",
  client_id_set: true,
  client_secret_set: true,
  user: "me",
  connected: true,
  lists: [
    { owner_user: "me", slug: "movies", name: "Movies" },
    { owner_user: "me", slug: "tv", name: "TV" },
  ],
}

describe("Lists page", () => {
  beforeEach(() => {
    vi.mocked(useTraktSettings).mockReturnValue(queryResult(sampleSettings))
  })

  it("renders the synced lists", () => {
    render(<Lists />)
    expect(screen.getByText("Lists")).toBeInTheDocument()
    expect(screen.getByText("Movies")).toBeInTheDocument()
    expect(screen.getByText("TV")).toBeInTheDocument()
    expect(screen.getByText("(me/movies)")).toBeInTheDocument()
  })

  it("shows an empty message when no lists are selected", () => {
    vi.mocked(useTraktSettings).mockReturnValue(
      queryResult({ ...sampleSettings, lists: [] }),
    )
    render(<Lists />)
    expect(screen.getByText("No lists selected yet.")).toBeInTheDocument()
  })
})
