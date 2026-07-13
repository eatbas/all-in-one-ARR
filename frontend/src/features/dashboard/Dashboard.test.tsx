import { fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useActivity: vi.fn(),
  useServiceStatuses: vi.fn(),
  useCheckServiceStatuses: vi.fn(),
  useServiceSettings: vi.fn(),
}))

import {
  useActivity,
  useCheckServiceStatuses,
  useServiceSettings,
  useServiceStatuses,
} from "@/shared/lib/queries"
import { Dashboard } from "@/features/dashboard/Dashboard"
import type {
  ActivityEntry,
  ServicesSettings,
  ServicesStatusResponse,
} from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"

const emptyServiceStatuses = {
  interval_seconds: 60,
  last_check_at: null,
  services: {},
}

const emptyServiceSettings: ServicesSettings = {
  seer: { url: "", api_key_set: false },
  sonarr: { url: "", api_key_set: false },
  radarr: { url: "", api_key_set: false },
  tmdb: { api_key_set: false },
  omdb: { api_key_set: false },
  sabnzbd: { url: "", api_key_set: false },
  qbittorrent: { url: "", api_key_set: false },
}

const checkNowMutate = vi.fn()

function activityEntries(count: number): ActivityEntry[] {
  return Array.from({ length: count }, (_, index) => {
    const id = index + 1

    return {
      id,
      ts: `2024-01-${String(id).padStart(2, "0")}T10:00:00Z`,
      action: `Action ${id}`,
      detail: `Detail ${id}`,
    }
  })
}

describe("Dashboard", () => {
  beforeEach(() => {
    checkNowMutate.mockClear()
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>([], false),
    )
    vi.mocked(useServiceStatuses).mockReturnValue(
      queryResult(emptyServiceStatuses, false),
    )
    vi.mocked(useServiceSettings).mockReturnValue(
      queryResult<ServicesSettings>(emptyServiceSettings, false),
    )
    vi.mocked(useCheckServiceStatuses).mockReturnValue({
      mutate: checkNowMutate,
      isPending: false,
    } as never)
  })

  it("starts with the activity feed collapsed", () => {
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>(
        [
          {
            id: 1,
            ts: "2024-01-01T10:00:00Z",
            action: "Requested",
            detail: "Dune",
          },
        ],
        false,
      ),
    )

    render(<Dashboard />)

    expect(
      screen.getByRole("heading", { name: "Dashboard" }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        "All-in-one ARR coordinates Trakt lists, Seer requests, Sonarr/Radarr searches, and download-client controls from one dashboard.",
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Integrations" })).toHaveClass(
      "text-2xl",
    )
    expect(
      screen.getByText(
        "Review the current connection status for every configured service.",
      ),
    ).toBeInTheDocument()
    const header = screen.getByRole("button", { name: /recent activity/i })
    expect(header).toHaveAttribute("aria-expanded", "false")
    expect(screen.getByText("Show")).toBeInTheDocument()
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument()
  })

  it("shows a loading placeholder while the activity query is loading", () => {
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>(undefined, true),
    )

    render(<Dashboard />)
    fireEvent.click(screen.getByRole("button", { name: /recent activity/i }))

    expect(screen.getByText("Loading activity…")).toBeInTheDocument()
  })

  it("shows an empty feed when settled but unpopulated", () => {
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>([], false),
    )

    render(<Dashboard />)
    fireEvent.click(screen.getByRole("button", { name: /recent activity/i }))

    expect(screen.getByText("No activity recorded yet.")).toBeInTheDocument()
  })

  it("renders a newest-first activity feed", () => {
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>(
        [
          {
            id: 1,
            ts: "2024-01-01T10:00:00Z",
            action: "Older",
            detail: "first",
          },
          { id: 2, ts: "not-a-date", action: "Newer", detail: "second" },
        ],
        false,
      ),
    )

    render(<Dashboard />)
    fireEvent.click(screen.getByRole("button", { name: /recent activity/i }))

    const entries = screen.getAllByRole("listitem")
    // Sorted by id descending: entry 2 ("Newer") comes first.
    expect(within(entries[0]).getByText("Newer")).toBeInTheDocument()
    expect(within(entries[1]).getByText("Older")).toBeInTheDocument()
    // An unparseable timestamp falls back to the raw string.
    expect(screen.getByText("not-a-date")).toBeInTheDocument()
  })

  it("shows five activity entries per page", () => {
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>(activityEntries(6), false),
    )

    render(<Dashboard />)
    fireEvent.click(screen.getByRole("button", { name: /recent activity/i }))

    const entries = screen.getAllByRole("listitem")
    expect(entries).toHaveLength(5)
    expect(within(entries[0]).getByText("Action 6")).toBeInTheDocument()
    expect(within(entries[4]).getByText("Action 2")).toBeInTheDocument()
    expect(screen.queryByText("Action 1")).not.toBeInTheDocument()
    expect(screen.getByText("Showing 1–5 of 6")).toBeInTheDocument()
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument()
  })

  it("pages through activity entries", async () => {
    const user = userEvent.setup()
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>(activityEntries(6), false),
    )

    render(<Dashboard />)
    await user.click(screen.getByRole("button", { name: /recent activity/i }))
    await user.click(screen.getByRole("button", { name: "Next activity page" }))

    const entries = screen.getAllByRole("listitem")
    expect(entries).toHaveLength(1)
    expect(within(entries[0]).getByText("Action 1")).toBeInTheDocument()
    expect(screen.getByText("Showing 6–6 of 6")).toBeInTheDocument()
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Next activity page" }),
    ).toBeDisabled()

    await user.click(
      screen.getByRole("button", { name: "Previous activity page" }),
    )

    expect(screen.getAllByRole("listitem")).toHaveLength(5)
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Previous activity page" }),
    ).toBeDisabled()
  })

  it("clamps the activity page when the activity feed shrinks", async () => {
    const user = userEvent.setup()
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>(activityEntries(6), false),
    )

    const { rerender } = render(<Dashboard />)
    await user.click(screen.getByRole("button", { name: /recent activity/i }))
    await user.click(screen.getByRole("button", { name: "Next activity page" }))
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument()

    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>(activityEntries(2), false),
    )
    rerender(<Dashboard />)

    const entries = screen.getAllByRole("listitem")
    expect(entries).toHaveLength(2)
    expect(within(entries[0]).getByText("Action 2")).toBeInTheDocument()
    expect(within(entries[1]).getByText("Action 1")).toBeInTheDocument()
    expect(screen.queryByText("Page 2 of 2")).not.toBeInTheDocument()
  })

  it("collapses and expands the activity feed when the header is clicked", async () => {
    const user = userEvent.setup()
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>(
        [
          {
            id: 1,
            ts: "2024-01-01T10:00:00Z",
            action: "Requested",
            detail: "Dune",
          },
        ],
        false,
      ),
    )

    render(<Dashboard />)
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument()
    expect(screen.getByText("Show")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /recent activity/i }))

    expect(screen.getByRole("listitem")).toBeInTheDocument()
    expect(screen.getByText("Hide")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /recent activity/i }))

    expect(screen.queryByRole("listitem")).not.toBeInTheDocument()
    expect(screen.getByText("Show")).toBeInTheDocument()
  })

  it("toggles the activity feed with the keyboard and ignores other keys", () => {
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>(
        [
          {
            id: 1,
            ts: "2024-01-01T10:00:00Z",
            action: "Requested",
            detail: "Dune",
          },
        ],
        false,
      ),
    )

    render(<Dashboard />)
    const header = screen.getByRole("button", { name: /recent activity/i })
    expect(header).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument()

    // A non-activating key leaves the feed closed.
    fireEvent.keyDown(header, { key: "a" })
    expect(header).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument()

    // Enter expands it.
    fireEvent.keyDown(header, { key: "Enter" })
    expect(header).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByRole("listitem")).toBeInTheDocument()

    // Space collapses it again.
    fireEvent.keyDown(header, { key: " " })
    expect(header).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument()
  })

  it("renders integration status cards", () => {
    vi.mocked(useServiceStatuses).mockReturnValue(
      queryResult(
        {
          interval_seconds: 60,
          last_check_at: "2026-06-23T13:22:46Z",
          services: {
            trakt: {
              ok: true,
              detail: "Connected",
              checked_at: "2026-06-23T13:22:46Z",
            },
            seer: {
              ok: false,
              detail: "Refused",
              checked_at: "2026-06-23T13:22:46Z",
            },
          },
        },
        false,
      ),
    )

    render(<Dashboard />)
    expect(screen.getByText("Integrations")).toBeInTheDocument()
    expect(
      screen.getByText("Trakt", { selector: "[data-slot='card-title']" }),
    ).toBeInTheDocument()
    expect(
      screen.getByText("Seer", { selector: "[data-slot='card-title']" }),
    ).toBeInTheDocument()
    const lastChecked = screen.getByText(/Last checked/)
    const checkNow = screen.getByRole("button", { name: /check now/i })
    expect(
      lastChecked.compareDocumentPosition(checkNow) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it("passes configured URLs to URL-bearing service cards", () => {
    vi.mocked(useServiceSettings).mockReturnValue(
      queryResult<ServicesSettings>(
        {
          ...emptyServiceSettings,
          seer: { url: "http://seer.example.com:5055", api_key_set: true },
          sonarr: { url: "http://sonarr.example.com:8989", api_key_set: true },
          sabnzbd: { url: "http://sab.example.com:8080", api_key_set: true },
        },
        false,
      ),
    )

    render(<Dashboard />)
    expect(screen.getByRole("link", { name: /Open Seer/ })).toHaveAttribute(
      "href",
      "http://seer.example.com:5055",
    )
    expect(screen.getByRole("link", { name: /Open Sonarr/ })).toHaveAttribute(
      "href",
      "http://sonarr.example.com:8989",
    )
    expect(screen.getByRole("link", { name: /Open SABnzbd/ })).toHaveAttribute(
      "href",
      "http://sab.example.com:8080",
    )
  })

  it("links Trakt and API-key-only services to their public sites", () => {
    render(<Dashboard />)
    expect(screen.getByRole("link", { name: /Open Trakt/ })).toHaveAttribute(
      "href",
      "https://trakt.tv",
    )
    expect(screen.getByRole("link", { name: /Open TMDB/ })).toHaveAttribute(
      "href",
      "https://www.themoviedb.org/",
    )
    expect(screen.getByRole("link", { name: /Open OMDb/ })).toHaveAttribute(
      "href",
      "https://www.omdbapi.com/",
    )
  })

  it("triggers a fresh check when 'Check now' is clicked", async () => {
    const user = userEvent.setup()
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>([], false),
    )

    render(<Dashboard />)
    await user.click(screen.getByRole("button", { name: /check now/i }))

    expect(checkNowMutate).toHaveBeenCalledTimes(1)
  })

  it("defaults services and spins the button while a check is pending", () => {
    vi.mocked(useActivity).mockReturnValue(
      queryResult<ActivityEntry[]>([], false),
    )
    // No service-status snapshot at all: `services` falls back to an empty map
    // and `lastCheck` is undefined.
    vi.mocked(useServiceStatuses).mockReturnValue(
      queryResult<ServicesStatusResponse>(undefined, false),
    )
    vi.mocked(useCheckServiceStatuses).mockReturnValue({
      mutate: checkNowMutate,
      isPending: true,
    } as never)

    render(<Dashboard />)
    // Renders without a snapshot (services defaults to an empty map) and the
    // pending check disables and spins the button.
    expect(screen.getByText("Integrations")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /check now/i })).toBeDisabled()
  })
})
