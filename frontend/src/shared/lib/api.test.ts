import { describe, expect, it, vi } from "vitest"

import {
  addTraktList,
  ApiError,
  checkServiceStatuses,
  clearActivity,
  clearItems,
  clearPosters,
  getActivity,
  getBandwidthStatus,
  getDatabaseStats,
  getGeneralSettings,
  getItems,
  getLists,
  getServiceSettings,
  getServiceStatuses,
  getStatus,
  getTraktAuthStatus,
  getTraktLists,
  getTraktSettings,
  seerMediaUrl,
  posterUrl,
  removeAvailable,
  removeItem,
  removeTraktList,
  startTraktAuth,
  testService,
  testTrakt,
  triggerSync,
  updateBandwidthSettings,
  updateGeneralSettings,
  updateServiceSettings,
  updateTraktSettings,
  type BandwidthStatus,
  type DatabaseStats,
  type Status,
} from "@/shared/lib/api"

/** Spy on the global fetch and resolve it with a ready-made Response. */
function mockFetch(response: Response) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(response)
}

function jsonResponse(body: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  })
}

const sampleStatus: Status = {
  trakt_connected: false,
  counts: { synced: 1, requested: 2, available: 3, removed: 4 },
}

describe("getStatus", () => {
  it("GETs /api/status with a JSON Accept header and parses the body", async () => {
    const fetchSpy = mockFetch(jsonResponse(sampleStatus))

    await expect(getStatus()).resolves.toEqual(sampleStatus)
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/status",
      expect.objectContaining({
        headers: expect.objectContaining({ Accept: "application/json" }),
      }),
    )
  })
})

describe("getItems", () => {
  it("omits the query string when no status filter is given", async () => {
    const fetchSpy = mockFetch(jsonResponse([]))

    await expect(getItems()).resolves.toEqual([])
    expect(fetchSpy).toHaveBeenCalledWith("/api/items", expect.anything())
  })

  it("appends an encoded status filter when one is given", async () => {
    const fetchSpy = mockFetch(jsonResponse([]))

    await getItems("requested")
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/items?status=requested",
      expect.anything(),
    )
  })

  it("appends the list filter on its own", async () => {
    const fetchSpy = mockFetch(jsonResponse([]))

    await getItems(undefined, "movies")
    expect(fetchSpy).toHaveBeenCalledWith("/api/items?list=movies", expect.anything())
  })

  it("combines the status and list filters", async () => {
    const fetchSpy = mockFetch(jsonResponse([]))

    await getItems("synced", "movies")
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/items?status=synced&list=movies",
      expect.anything(),
    )
  })
})

describe("getLists", () => {
  it("GETs /api/lists", async () => {
    const fetchSpy = mockFetch(jsonResponse([]))

    await expect(getLists()).resolves.toEqual([])
    expect(fetchSpy).toHaveBeenCalledWith("/api/lists", expect.anything())
  })
})

describe("posterUrl", () => {
  it("builds the same-origin poster path for an item", () => {
    expect(posterUrl("movie", 603)).toBe("/api/posters/movie/603")
    expect(posterUrl("show", 1399)).toBe("/api/posters/show/1399")
  })
})

describe("seerMediaUrl", () => {
  it("maps the media type onto Overseerr/Seer routes", () => {
    expect(seerMediaUrl("https://req.example.com", "movie", 603)).toBe(
      "https://req.example.com/movie/603",
    )
    expect(seerMediaUrl("https://req.example.com", "show", 1399)).toBe(
      "https://req.example.com/tv/1399",
    )
  })

  it("trims trailing slashes from the base URL", () => {
    expect(seerMediaUrl("https://req.example.com///", "movie", 603)).toBe(
      "https://req.example.com/movie/603",
    )
  })
})

describe("removeItem", () => {
  it("DELETEs the encoded item path", async () => {
    const fetchSpy = mockFetch(jsonResponse({ status: "removed" }))
    await removeItem("my list", 438631)
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/items/my%20list/438631",
      expect.objectContaining({ method: "DELETE" }),
    )
  })
})

describe("removeAvailable", () => {
  it("POSTs the remove-available trigger", async () => {
    const fetchSpy = mockFetch(jsonResponse({ status: "triggered" }))
    await removeAvailable()
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/items/remove-available",
      expect.objectContaining({ method: "POST" }),
    )
  })
})

describe("getActivity", () => {
  it("GETs /api/activity", async () => {
    const fetchSpy = mockFetch(jsonResponse([]))

    await expect(getActivity()).resolves.toEqual([])
    expect(fetchSpy).toHaveBeenCalledWith("/api/activity", expect.anything())
  })
})

describe("triggerSync", () => {
  it("POSTs an empty JSON body to /api/sync and returns completed", async () => {
    const fetchSpy = mockFetch(jsonResponse({ status: "completed" }))

    await expect(triggerSync()).resolves.toEqual({ status: "completed" })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/sync",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Accept: "application/json",
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({}),
      }),
    )
  })
})

describe("trakt settings and lists", () => {
  it("GETs the trakt settings", async () => {
    const fetchSpy = mockFetch(jsonResponse({ user: "me" }))
    await getTraktSettings()
    expect(fetchSpy).toHaveBeenCalledWith("/api/settings/trakt", expect.anything())
  })

  it("PUTs updated trakt settings", async () => {
    const fetchSpy = mockFetch(jsonResponse({ client_id_hint: "1234" }))
    await updateTraktSettings({ client_id: "newid1234" })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/settings/trakt",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ client_id: "newid1234" }),
      }),
    )
  })

  it("POSTs to start device auth", async () => {
    const fetchSpy = mockFetch(jsonResponse({ state: "pending" }))
    await startTraktAuth()
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/trakt/auth/start",
      expect.objectContaining({ method: "POST" }),
    )
  })

  it("GETs the device-auth status", async () => {
    const fetchSpy = mockFetch(jsonResponse({ state: "idle", connected: false }))
    await getTraktAuthStatus()
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/trakt/auth/status",
      expect.anything(),
    )
  })

  it("POSTs a connection test", async () => {
    const fetchSpy = mockFetch(jsonResponse({ ok: true, user: "me", message: "" }))
    await testTrakt()
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/trakt/test",
      expect.objectContaining({ method: "POST" }),
    )
  })

  it("GETs the discoverable lists", async () => {
    const fetchSpy = mockFetch(jsonResponse([]))
    await getTraktLists()
    expect(fetchSpy).toHaveBeenCalledWith("/api/trakt/lists", expect.anything())
  })

  it("POSTs a list to add", async () => {
    const fetchSpy = mockFetch(jsonResponse({ lists: [] }))
    await addTraktList({ url: "https://trakt.tv/users/me/lists/anime" })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/trakt/lists",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ url: "https://trakt.tv/users/me/lists/anime" }),
      }),
    )
  })

  it("DELETEs a list, encoding the path segments", async () => {
    const fetchSpy = mockFetch(jsonResponse({ lists: [] }))
    await removeTraktList("me", "my list")
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/trakt/lists/me/my%20list",
      expect.objectContaining({ method: "DELETE" }),
    )
  })
})

describe("service settings", () => {
  it("GETs the service settings", async () => {
    const fetchSpy = mockFetch(jsonResponse({}))
    await getServiceSettings()
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/settings/services",
      expect.anything(),
    )
  })

  it("PUTs a service update to the named path", async () => {
    const fetchSpy = mockFetch(jsonResponse({}))
    await updateServiceSettings("sonarr", { url: "http://sonarr:8989" })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/settings/services/sonarr",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ url: "http://sonarr:8989" }),
      }),
    )
  })

  it("POSTs a service connection test", async () => {
    const fetchSpy = mockFetch(jsonResponse({ ok: true, detail: "" }))
    await testService("radarr")
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/services/radarr/test",
      expect.objectContaining({ method: "POST" }),
    )
  })
})

describe("service status dashboard", () => {
  it("GETs the cached service statuses", async () => {
    const fetchSpy = mockFetch(
      jsonResponse({
        interval_seconds: 60,
        last_check_at: null,
        services: {},
      }),
    )
    await getServiceStatuses()
    expect(fetchSpy).toHaveBeenCalledWith("/api/status/services", expect.anything())
  })

  it("POSTs to trigger a fresh status check", async () => {
    const fetchSpy = mockFetch(
      jsonResponse({
        interval_seconds: 60,
        last_check_at: "2026-06-23T13:22:46Z",
        services: {},
      }),
    )
    await checkServiceStatuses()
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/status/services/check",
      expect.objectContaining({ method: "POST" }),
    )
  })
})

describe("general settings", () => {
  it("GETs the general settings", async () => {
    const fetchSpy = mockFetch(jsonResponse({ interval_seconds: 60 }))
    await getGeneralSettings()
    expect(fetchSpy).toHaveBeenCalledWith("/api/settings/general", expect.anything())
  })

  it("PUTs the status-check interval", async () => {
    const fetchSpy = mockFetch(jsonResponse({ interval_seconds: 30 }))
    await updateGeneralSettings({ interval_seconds: 30 })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/settings/general",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ interval_seconds: 30 }),
      }),
    )
  })
})

const sampleDatabaseStats: DatabaseStats = {
  db_size_bytes: 1024,
  poster_cache_bytes: 2048,
  item_count: 5,
  activity_count: 12,
  list_state_count: 2,
}

describe("database settings", () => {
  it("GETs the database stats", async () => {
    const fetchSpy = mockFetch(jsonResponse(sampleDatabaseStats))
    await expect(getDatabaseStats()).resolves.toEqual(sampleDatabaseStats)
    expect(fetchSpy).toHaveBeenCalledWith("/api/settings/database", expect.anything())
  })

  it("POSTs to clear the activity log", async () => {
    const fetchSpy = mockFetch(jsonResponse(sampleDatabaseStats))
    await expect(clearActivity()).resolves.toEqual(sampleDatabaseStats)
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/settings/database/clear-activity",
      expect.objectContaining({ method: "POST" }),
    )
  })

  it("POSTs to clear synced items and sync state", async () => {
    const fetchSpy = mockFetch(jsonResponse(sampleDatabaseStats))
    await expect(clearItems()).resolves.toEqual(sampleDatabaseStats)
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/settings/database/clear-items",
      expect.objectContaining({ method: "POST" }),
    )
  })

  it("POSTs to clear the poster cache", async () => {
    const fetchSpy = mockFetch(jsonResponse(sampleDatabaseStats))
    await expect(clearPosters()).resolves.toEqual(sampleDatabaseStats)
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/settings/database/clear-posters",
      expect.objectContaining({ method: "POST" }),
    )
  })
})

const sampleBandwidthStatus: BandwidthStatus = {
  enabled: false,
  status: "Monitoring only",
  last_run_at: "2026-06-26T20:00:00Z",
  check_interval_seconds: 15,
  qbittorrent: {
    online: true,
    speed_mbps: 12.5,
    active_downloads: 2,
    queue_size: 1,
  },
  sabnzbd: {
    online: true,
    speed_mbps: 0,
    active_downloads: 0,
    queue_size: 0,
    paused: false,
  },
}

describe("bandwidth controllarr", () => {
  it("GETs the bandwidth status", async () => {
    const fetchSpy = mockFetch(jsonResponse(sampleBandwidthStatus))
    await expect(getBandwidthStatus()).resolves.toEqual(sampleBandwidthStatus)
    expect(fetchSpy).toHaveBeenCalledWith("/api/bandwidth/status", expect.anything())
  })

  it("PUTs bandwidth settings", async () => {
    const fetchSpy = mockFetch(jsonResponse(sampleBandwidthStatus))
    await expect(updateBandwidthSettings({ enabled: true })).resolves.toEqual(
      sampleBandwidthStatus,
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/bandwidth/settings",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ enabled: true }),
      }),
    )
  })
})

describe("request error and empty-body handling", () => {
  it("throws a typed ApiError on a non-2xx response", async () => {
    mockFetch(new Response("nope", { status: 503 }))

    const error = await getStatus().catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(503)
    expect((error as ApiError).name).toBe("ApiError")
    expect((error as ApiError).message).toContain("/api/status")
    expect((error as ApiError).message).toContain("503")
  })

  it("resolves to undefined when the response body is empty", async () => {
    mockFetch(new Response("", { status: 202 }))

    await expect(triggerSync()).resolves.toBeUndefined()
  })
})
