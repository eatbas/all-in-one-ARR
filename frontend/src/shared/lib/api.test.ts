import { describe, expect, it, vi } from "vitest"

import {
  addTraktList,
  ApiError,
  checkServiceStatuses,
  getActivity,
  getGeneralSettings,
  getItems,
  getServiceSettings,
  getServiceStatuses,
  getStatus,
  getTraktAuthStatus,
  getTraktLists,
  getTraktSettings,
  removeTraktList,
  setDryRun,
  startTraktAuth,
  testService,
  testTrakt,
  triggerSync,
  updateGeneralSettings,
  updateServiceSettings,
  updateTraktSettings,
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
  dry_run: true,
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
})

describe("getActivity", () => {
  it("GETs /api/activity", async () => {
    const fetchSpy = mockFetch(jsonResponse([]))

    await expect(getActivity()).resolves.toEqual([])
    expect(fetchSpy).toHaveBeenCalledWith("/api/activity", expect.anything())
  })
})

describe("triggerSync", () => {
  it("POSTs an empty JSON body to /api/sync", async () => {
    const fetchSpy = mockFetch(jsonResponse({ status: "triggered" }))

    await expect(triggerSync()).resolves.toEqual({ status: "triggered" })
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

describe("setDryRun", () => {
  it("POSTs the enabled flag to /api/settings/dry-run", async () => {
    const fetchSpy = mockFetch(jsonResponse({ dry_run: false }))

    await expect(setDryRun(false)).resolves.toEqual({ dry_run: false })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/settings/dry-run",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Accept: "application/json",
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({ enabled: false }),
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
    const fetchSpy = mockFetch(jsonResponse({ user: "bob" }))
    await updateTraktSettings({ user: "bob" })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/settings/trakt",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ user: "bob" }),
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
