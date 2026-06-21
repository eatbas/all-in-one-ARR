import { describe, expect, it, vi } from "vitest"

import {
  ApiError,
  getActivity,
  getItems,
  getStatus,
  setDryRun,
  triggerSync,
  type Status,
} from "@/lib/api"

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
