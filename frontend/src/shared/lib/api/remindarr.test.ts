import { afterEach, describe, expect, it, vi } from "vitest"

import {
  getRemindarrResults,
  getRemindarrSettings,
  getRemindarrStatus,
  getRemindarrTags,
  REMINDARR_MAX_TAGS,
  runRemindarr,
  updateRemindarrSettings,
} from "@/shared/lib/api/remindarr"

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

describe("Remindarr API", () => {
  it("mirrors the backend's tag limit", () => {
    expect(REMINDARR_MAX_TAGS).toBe(50)
  })

  it.each([
    ["status", getRemindarrStatus, "/api/remindarr/status"],
    ["settings", getRemindarrSettings, "/api/remindarr/settings"],
    ["tags", getRemindarrTags, "/api/remindarr/tags"],
    ["results", getRemindarrResults, "/api/remindarr/results"],
  ])("GETs the %s", async (_name, call, url) => {
    const fetchSpy = mockFetch({ ok: true })
    await expect(call()).resolves.toEqual({ ok: true })
    expect(fetchSpy).toHaveBeenCalledWith(url, expect.anything())
  })

  it("PUTs settings", async () => {
    const fetchSpy = mockFetch({})
    await updateRemindarrSettings({ tag_ids: [1, 2] })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/remindarr/settings",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ tag_ids: [1, 2] }),
      }),
    )
  })

  it("POSTs a manual refresh", async () => {
    const fetchSpy = mockFetch({ status: "success" })
    await expect(runRemindarr()).resolves.toEqual({ status: "success" })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/remindarr/run",
      expect.objectContaining({ method: "POST", body: "{}" }),
    )
  })
})
