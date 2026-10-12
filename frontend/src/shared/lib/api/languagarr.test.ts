import { afterEach, describe, expect, it, vi } from "vitest"

import {
  clearLanguagarrPending,
  deleteLanguagarr,
  enqueueLanguagarr,
  getLanguagarrQueue,
  getLanguagarrResults,
  getLanguagarrSettings,
  getLanguagarrStatus,
  runLanguagarr,
  scanLanguagarr,
  sonarrSeriesUrl,
  updateLanguagarrSettings,
} from "@/shared/lib/api/languagarr"

function mockFetch(body: unknown) {
  // A fresh Response per call: a body can only be read once.
  return vi.spyOn(globalThis, "fetch").mockImplementation(
    async () =>
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  )
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe("sonarrSeriesUrl", () => {
  it("joins the base URL and an encoded title slug", () => {
    expect(sonarrSeriesUrl("http://192.168.0.2:8989/", "log-horizon")).toBe(
      "http://192.168.0.2:8989/series/log-horizon",
    )
    expect(sonarrSeriesUrl("https://nas.lan/sonarr", "a b")).toBe(
      "https://nas.lan/sonarr/series/a%20b",
    )
  })
})

describe("Languagarr API", () => {
  it.each([
    ["status", getLanguagarrStatus, "/api/languagarr/status"],
    ["settings", getLanguagarrSettings, "/api/languagarr/settings"],
    ["results", getLanguagarrResults, "/api/languagarr/results"],
    ["queue", getLanguagarrQueue, "/api/languagarr/queue"],
  ])("GETs the %s", async (_name, call, url) => {
    const fetchSpy = mockFetch({ ok: true })
    await expect(call()).resolves.toEqual({ ok: true })
    expect(fetchSpy).toHaveBeenCalledWith(url, expect.anything())
  })

  it("PUTs settings", async () => {
    const fetchSpy = mockFetch({})
    await updateLanguagarrSettings({ enabled: true })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/languagarr/settings",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ enabled: true }),
      }),
    )
  })

  it("POSTs scan, run and enqueue", async () => {
    const fetchSpy = mockFetch({})
    await scanLanguagarr()
    await runLanguagarr()
    await enqueueLanguagarr([1, 2])
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/languagarr/scan",
      expect.objectContaining({ method: "POST", body: "{}" }),
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/languagarr/run",
      expect.objectContaining({ method: "POST" }),
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/languagarr/enqueue",
      expect.objectContaining({
        body: JSON.stringify({ episode_file_ids: [1, 2] }),
      }),
    )
  })

  it("always sends an explicit confirmation with a delete", async () => {
    const fetchSpy = mockFetch({})
    await deleteLanguagarr([3])
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/languagarr/delete",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ episode_file_ids: [3], confirm: true }),
      }),
    )
  })

  it("DELETEs pending queue rows", async () => {
    const fetchSpy = mockFetch({ removed: 2 })
    await expect(clearLanguagarrPending()).resolves.toEqual({ removed: 2 })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/languagarr/queue/pending",
      expect.objectContaining({ method: "DELETE" }),
    )
  })
})
