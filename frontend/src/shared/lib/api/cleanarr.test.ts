import { afterEach, describe, expect, it, vi } from "vitest"

import {
  cleanarrErrorMessage,
  clearCleanarrStrikes,
  getCleanarrHistory,
  getCleanarrQueue,
  getCleanarrSettings,
  getCleanarrStatus,
  ignoreCleanarrDownload,
  runCleanarr,
  updateCleanarrSettings,
} from "@/shared/lib/api/cleanarr"
import { ApiError } from "@/shared/lib/api/client"

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

describe("Cleanarr API", () => {
  it.each([
    ["status", getCleanarrStatus, "/api/cleanarr/status"],
    ["settings", getCleanarrSettings, "/api/cleanarr/settings"],
    ["queue", getCleanarrQueue, "/api/cleanarr/queue"],
    ["history", getCleanarrHistory, "/api/cleanarr/history"],
  ])("GETs the %s", async (_name, call, url) => {
    const fetchSpy = mockFetch({ ok: true })
    await expect(call()).resolves.toEqual({ ok: true })
    expect(fetchSpy).toHaveBeenCalledWith(url, expect.anything())
  })

  it("PUTs settings updates as JSON", async () => {
    const fetchSpy = mockFetch({ ok: true })
    await updateCleanarrSettings({ dry_run: false })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/cleanarr/settings",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ dry_run: false }),
      }),
    )
  })

  it.each([
    ["run", runCleanarr, "/api/cleanarr/run", {}],
    ["clear strikes", clearCleanarrStrikes, "/api/cleanarr/strikes/clear", {}],
  ])("POSTs %s", async (_name, call, url, body) => {
    const fetchSpy = mockFetch({ ok: true })
    await call()
    expect(fetchSpy).toHaveBeenCalledWith(
      url,
      expect.objectContaining({ method: "POST", body: JSON.stringify(body) }),
    )
  })

  it("POSTs the download id to ignore", async () => {
    const fetchSpy = mockFetch({ ok: true })
    await ignoreCleanarrDownload("SABnzbd_nzo_1")
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/cleanarr/ignore",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ download_id: "SABnzbd_nzo_1" }),
      }),
    )
  })
})

describe("cleanarrErrorMessage", () => {
  it("names each invalid field of a FastAPI validation array", () => {
    const error = new ApiError(422, "Request failed with status 422", [
      { loc: ["body", "orphans", "min_age_hours"], msg: "Input should be ≥ 1" },
      { loc: ["query", "page"], msg: "Field required" },
      null,
      "not an issue",
      { loc: "body", msg: "loc is not a list" },
    ])
    expect(cleanarrErrorMessage(error)).toBe(
      "Minimum age (hours): Input should be ≥ 1; query.page: Field required",
    )
  })

  it("keeps the message of any other error", () => {
    expect(cleanarrErrorMessage(new Error("offline"))).toBe("offline")
    expect(cleanarrErrorMessage(new ApiError(500, "broken"))).toBe("broken")
  })
})
