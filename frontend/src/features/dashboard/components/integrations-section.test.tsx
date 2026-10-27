import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useServiceStatuses: vi.fn(),
  useCheckServiceStatuses: vi.fn(),
  useServiceSettings: vi.fn(),
}))

import {
  useCheckServiceStatuses,
  useServiceSettings,
  useServiceStatuses,
} from "@/shared/lib/queries"
import type { ServicesSettings, ServicesStatusResponse } from "@/shared/lib/api"
import { SERVICE_TABS } from "@/shared/lib/services"
import { mutationResult, queryResult } from "@/shared/test/mock-query"
import { IntegrationsSection } from "@/features/dashboard/components/integrations-section"

const emptyServiceStatuses: ServicesStatusResponse = {
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

describe("IntegrationsSection", () => {
  beforeEach(() => {
    checkNowMutate.mockClear()
    vi.mocked(useServiceStatuses).mockReturnValue(
      queryResult(emptyServiceStatuses, false),
    )
    vi.mocked(useServiceSettings).mockReturnValue(
      queryResult<ServicesSettings>(emptyServiceSettings, false),
    )
    vi.mocked(useCheckServiceStatuses).mockReturnValue(
      mutationResult(checkNowMutate, false),
    )
  })

  it("renders the heading, description and a card for Trakt plus every service", () => {
    render(<IntegrationsSection />)

    expect(screen.getByRole("heading", { name: "Integrations" })).toHaveClass(
      "text-2xl",
    )
    expect(
      screen.getByText(
        "Review the current connection status for every configured service.",
      ),
    ).toBeInTheDocument()
    expect(screen.getByText("Not checked yet")).toBeInTheDocument()
    for (const label of ["Trakt", ...SERVICE_TABS.map((tab) => tab.label)]) {
      expect(
        screen.getByText(label, { selector: "[data-slot='card-title']" }),
      ).toBeInTheDocument()
    }
    expect(
      screen
        .getByText("Trakt", { selector: "[data-slot='card-title']" })
        .closest(".grid"),
    ).toHaveClass("grid-cols-2", "gap-3", "sm:grid-cols-4")
  })

  it("renders integration status and the last check before 'Check now'", () => {
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

    render(<IntegrationsSection />)
    const lastChecked = screen.getByText(/Last checked/)
    const checkNow = screen.getByRole("button", { name: /check now/i })
    expect(
      lastChecked.compareDocumentPosition(checkNow) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(screen.getByTitle("Refused")).toBeInTheDocument()
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

    render(<IntegrationsSection />)
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

  it("points Docker-internal service URLs at the host the browser used", () => {
    vi.mocked(useServiceSettings).mockReturnValue(
      queryResult<ServicesSettings>(
        {
          ...emptyServiceSettings,
          sonarr: { url: "http://sonarr:8989", api_key_set: true },
          radarr: { url: "http://localhost:7878", api_key_set: true },
        },
        false,
      ),
    )

    render(<IntegrationsSection />)
    const { hostname } = window.location
    expect(screen.getByRole("link", { name: /Open Sonarr/ })).toHaveAttribute(
      "href",
      `http://${hostname}:8989`,
    )
    expect(screen.getByRole("link", { name: /Open Radarr/ })).toHaveAttribute(
      "href",
      `http://${hostname}:7878`,
    )
  })

  it("links Trakt and API-key-only services to their public sites", () => {
    render(<IntegrationsSection />)
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
    render(<IntegrationsSection />)

    await user.click(screen.getByRole("button", { name: /check now/i }))

    expect(checkNowMutate).toHaveBeenCalledTimes(1)
  })

  it("disables 'Check now' while statuses load", () => {
    vi.mocked(useServiceStatuses).mockReturnValue(
      queryResult<ServicesStatusResponse>(undefined, true),
    )
    render(<IntegrationsSection />)

    expect(screen.getByRole("button", { name: /check now/i })).toBeDisabled()
  })

  it("defaults services and spins the button while a check is pending", () => {
    vi.mocked(useServiceStatuses).mockReturnValue(
      queryResult<ServicesStatusResponse>(undefined, false),
    )
    vi.mocked(useCheckServiceStatuses).mockReturnValue(
      mutationResult(checkNowMutate, true),
    )

    render(<IntegrationsSection />)

    const button = screen.getByRole("button", { name: /check now/i })
    expect(button).toBeDisabled()
    expect(button.querySelector("svg")).toHaveClass("animate-spin")
  })
})
