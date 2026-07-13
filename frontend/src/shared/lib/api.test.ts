import { describe, expect, it, vi } from "vitest"

import {
  addTraktList,
  addTrending,
  ApiError,
  checkServiceStatuses,
  clearActivity,
  clearFindarrHistory,
  clearItems,
  clearPosters,
  deleteDeletarrItems,
  getActivity,
  getDatabaseStats,
  getDeletarrResults,
  getDeletarrSettings,
  getDeletarrStatus,
  getFindarrHistory,
  getFindarrSettings,
  getFindarrStatus,
  getGeneralSettings,
  getItems,
  getLists,
  getServiceSettings,
  getServiceStatuses,
  getStatus,
  getTraktAuthStatus,
  getTraktLists,
  getTraktSettings,
  getTrending,
  getTrendingStatus,
  searchTrending,
  trendingSourceUrl,
  seerMediaUrl,
  normaliseServiceUrl,
  isLikelyInternalUrl,
  posterUrl,
  removeAvailable,
  removeItem,
  removeTraktList,
  resetFindarrState,
  runFindarr,
  scanDeletarr,
  startTraktAuth,
  testService,
  testTrakt,
  triggerSync,
  updateDeletarrSettings,
  updateFindarrSettings,
  updateGeneralSettings,
  updateServiceSettings,
  updateTraktSettings,
  type DatabaseStats,
  type Status,
  type TrendingItem,
} from "@/shared/lib/api"

/** Build a TrendingItem fixture for the source-URL helper tests. */
function trendingItem(over: Partial<TrendingItem>): TrendingItem {
  return {
    source: "tmdb",
    media_type: "movie",
    tmdb: 603,
    imdb: null,
    tvdb: null,
    trakt: null,
    slug: null,
    title: "X",
    year: 2000,
    anilist: null,
    poster_url: null,
    seer_status: null,
    imdb_rating: null,
    already_tracked: false,
    in_library: false,
    in_library_available: false,
    ...over,
  }
}

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
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/items?list=movies",
      expect.anything(),
    )
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

  it("includes an IMDb fallback id when one is available", () => {
    expect(posterUrl("movie", 603, "tt0133093")).toBe(
      "/api/posters/movie/603?imdb=tt0133093",
    )
    expect(posterUrl("movie", 603, null)).toBe("/api/posters/movie/603")
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

describe("normaliseServiceUrl", () => {
  it("adds http:// when no scheme is present", () => {
    expect(normaliseServiceUrl("seer:5055")).toBe("http://seer:5055")
  })

  it("trims whitespace and trailing slashes", () => {
    expect(normaliseServiceUrl("  http://js:5055/  ")).toBe("http://js:5055")
    expect(normaliseServiceUrl("https://req.example.com/path/")).toBe(
      "https://req.example.com/path",
    )
  })

  it("returns an empty string for an empty input", () => {
    expect(normaliseServiceUrl("")).toBe("")
  })

  it("rejects unsupported schemes", () => {
    expect(() => normaliseServiceUrl("ftp://host")).toThrow(
      "http:// or https://",
    )
    expect(() => normaliseServiceUrl("file:///etc/passwd")).toThrow(
      "http:// or https://",
    )
  })
})

describe("isLikelyInternalUrl", () => {
  it("flags single-label hostnames and localhost", () => {
    expect(isLikelyInternalUrl("http://seer:5055")).toBe(true)
    expect(isLikelyInternalUrl("http://sonarr:8989")).toBe(true)
    expect(isLikelyInternalUrl("http://localhost:5055")).toBe(true)
    expect(isLikelyInternalUrl("http://127.0.0.1:5055")).toBe(true)
  })

  it("does not flag hostnames with dots", () => {
    expect(isLikelyInternalUrl("http://192.168.1.5:5055")).toBe(false)
    expect(isLikelyInternalUrl("https://seer.example.com")).toBe(false)
  })

  it("is forgiving with malformed input", () => {
    expect(isLikelyInternalUrl("")).toBe(false)
    expect(isLikelyInternalUrl("not a url")).toBe(false)
    expect(isLikelyInternalUrl("ftp://host")).toBe(false)
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
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/settings/trakt",
      expect.anything(),
    )
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
    const fetchSpy = mockFetch(
      jsonResponse({ state: "idle", connected: false }),
    )
    await getTraktAuthStatus()
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/trakt/auth/status",
      expect.anything(),
    )
  })

  it("POSTs a connection test", async () => {
    const fetchSpy = mockFetch(
      jsonResponse({ ok: true, user: "me", message: "" }),
    )
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
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/status/services",
      expect.anything(),
    )
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
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/settings/general",
      expect.anything(),
    )
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
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/settings/database",
      expect.anything(),
    )
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

describe("deletarr", () => {
  it("GETs the Deletarr status and settings", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ settings: {}, libraries: {} }))
      .mockResolvedValueOnce(jsonResponse({ movies_path: "/media/movies" }))

    await getDeletarrStatus()
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/deletarr/status",
      expect.anything(),
    )

    await getDeletarrSettings()
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/deletarr/settings",
      expect.anything(),
    )
  })

  it("PUTs Deletarr settings", async () => {
    const fetchSpy = mockFetch(jsonResponse({ settings: {}, libraries: {} }))

    await updateDeletarrSettings({ movies_path: "/srv/movies" })

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/deletarr/settings",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ movies_path: "/srv/movies" }),
      }),
    )
  })

  it("GETs results for the requested library", async () => {
    const fetchSpy = mockFetch(jsonResponse({ type: "movies", results: [] }))

    await getDeletarrResults("movies")

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/deletarr/results?type=movies",
      expect.anything(),
    )
  })

  it("POSTs scan and delete requests", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ type: "movies", results: [] }))
      .mockResolvedValueOnce(jsonResponse({ success: true, deleted: 1 }))

    await scanDeletarr("movies")
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/deletarr/scan",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ type: "movies" }),
      }),
    )

    await deleteDeletarrItems("tv", ["/media/tv/Show/sample.txt"])
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/deletarr/delete",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          type: "tv",
          paths: ["/media/tv/Show/sample.txt"],
        }),
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

  it("surfaces the backend's JSON detail as the error message", async () => {
    mockFetch(
      new Response(
        JSON.stringify({ detail: "Trakt could not find this title to add" }),
        {
          status: 502,
          headers: { "Content-Type": "application/json" },
        },
      ),
    )

    const error = await getStatus().catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(502)
    expect((error as ApiError).message).toBe(
      "Trakt could not find this title to add",
    )
  })

  it("falls back to the status message when detail is not a string", async () => {
    // FastAPI validation errors return `detail` as an array, not a string.
    mockFetch(
      new Response(JSON.stringify({ detail: [{ msg: "bad" }] }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      }),
    )

    const error = await getStatus().catch((caught: unknown) => caught)
    expect((error as ApiError).message).toContain("/api/status")
    expect((error as ApiError).message).toContain("422")
  })

  it("resolves to undefined when the response body is empty", async () => {
    mockFetch(new Response("", { status: 202 }))

    await expect(triggerSync()).resolves.toBeUndefined()
  })
})

describe("getTrending", () => {
  it("builds the query string from the source/media/category", async () => {
    const fetchSpy = mockFetch(jsonResponse([]))

    await expect(
      getTrending({ source: "trakt", media: "movie", category: "trending" }),
    ).resolves.toEqual([])
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).toContain("source=trakt")
    expect(url).toContain("media=movie")
    expect(url).toContain("category=trending")
    // The time window was removed, so no `window` param is ever sent.
    expect(url).not.toContain("window=")
  })
})

describe("searchTrending", () => {
  it("builds the query string from the source/media/query", async () => {
    const fetchSpy = mockFetch(jsonResponse([]))

    await expect(
      searchTrending({ source: "tmdb", media: "show", query: "dan da dan" }),
    ).resolves.toEqual([])
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).toContain("/api/trending/search?")
    expect(url).toContain("source=tmdb")
    expect(url).toContain("media=show")
    // URLSearchParams encodes spaces as `+`.
    expect(url).toContain("query=dan+da+dan")
  })
})

describe("getTrendingStatus", () => {
  it("fetches the scheduled-sync status", async () => {
    const fetchSpy = mockFetch(
      jsonResponse({
        last_synced_at: "2026-06-30T12:00:00+00:00",
        interval_minutes: 60,
        next_sync_at: "2026-06-30T13:00:00+00:00",
      }),
    )

    await expect(getTrendingStatus()).resolves.toEqual({
      last_synced_at: "2026-06-30T12:00:00+00:00",
      interval_minutes: 60,
      next_sync_at: "2026-06-30T13:00:00+00:00",
    })
    expect(fetchSpy.mock.calls[0][0]).toBe("/api/trending/status")
  })
})

describe("addTrending", () => {
  it("POSTs the payload as JSON", async () => {
    const fetchSpy = mockFetch(jsonResponse({ status: "added" }))

    await expect(
      addTrending({
        media_type: "movie",
        owner_user: "me",
        slug: "my-list",
        tmdb: 100,
      }),
    ).resolves.toEqual({ status: "added" })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/trending/add",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          media_type: "movie",
          owner_user: "me",
          slug: "my-list",
          tmdb: 100,
        }),
      }),
    )
  })
})

describe("trendingSourceUrl", () => {
  it("links TMDB movies and shows by TMDB id", () => {
    expect(trendingSourceUrl(trendingItem({ source: "tmdb", tmdb: 603 }))).toBe(
      "https://www.themoviedb.org/movie/603",
    )
    expect(
      trendingSourceUrl(
        trendingItem({ source: "tmdb", media_type: "show", tmdb: 1399 }),
      ),
    ).toBe("https://www.themoviedb.org/tv/1399")
  })

  it("returns null for a TMDB item with no TMDB id", () => {
    expect(
      trendingSourceUrl(trendingItem({ source: "tmdb", tmdb: null })),
    ).toBeNull()
  })

  it("links Trakt movies and shows by slug", () => {
    expect(
      trendingSourceUrl(trendingItem({ source: "trakt", slug: "dune-2021" })),
    ).toBe("https://trakt.tv/movies/dune-2021")
    expect(
      trendingSourceUrl(
        trendingItem({
          source: "trakt",
          media_type: "show",
          slug: "severance",
        }),
      ),
    ).toBe("https://trakt.tv/shows/severance")
  })

  it("returns null for a Trakt item without a slug", () => {
    expect(
      trendingSourceUrl(trendingItem({ source: "trakt", slug: null })),
    ).toBeNull()
  })

  it("links the anime variants like their base sources", () => {
    expect(
      trendingSourceUrl(
        trendingItem({
          source: "tmdb-anime",
          media_type: "show",
          tmdb: 240411,
        }),
      ),
    ).toBe("https://www.themoviedb.org/tv/240411")
    expect(
      trendingSourceUrl(
        trendingItem({
          source: "trakt-anime",
          media_type: "show",
          slug: "dan-da-dan",
        }),
      ),
    ).toBe("https://trakt.tv/shows/dan-da-dan")
  })

  it("links AniList items by AniList id for both media types", () => {
    expect(
      trendingSourceUrl(
        trendingItem({
          source: "anilist",
          media_type: "show",
          anilist: 195600,
        }),
      ),
    ).toBe("https://anilist.co/anime/195600")
    // AniList uses one /anime/ route for movies too.
    expect(
      trendingSourceUrl(
        trendingItem({
          source: "anilist",
          media_type: "movie",
          anilist: 21519,
        }),
      ),
    ).toBe("https://anilist.co/anime/21519")
  })

  it("returns null for an AniList item with no AniList id", () => {
    expect(
      trendingSourceUrl(trendingItem({ source: "anilist", anilist: null })),
    ).toBeNull()
  })

  it("links Seer items to the configured instance via seerMediaUrl", () => {
    expect(
      trendingSourceUrl(
        trendingItem({ source: "seer", tmdb: 42 }),
        "https://seer.example.com/",
      ),
    ).toBe("https://seer.example.com/movie/42")
  })

  it("returns null for a Seer item with no base URL or no TMDB id", () => {
    expect(
      trendingSourceUrl(trendingItem({ source: "seer", tmdb: 42 })),
    ).toBeNull()
    expect(
      trendingSourceUrl(
        trendingItem({ source: "seer", tmdb: null }),
        "https://seer.example.com",
      ),
    ).toBeNull()
  })
})

describe("findarr", () => {
  it("GETs the Findarr status", async () => {
    const fetchSpy = mockFetch(jsonResponse({ running: false }))
    await getFindarrStatus()
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/findarr/status",
      expect.anything(),
    )
  })

  it("GETs the Findarr settings", async () => {
    const fetchSpy = mockFetch(jsonResponse({ enabled: false }))
    await getFindarrSettings()
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/findarr/settings",
      expect.anything(),
    )
  })

  it("PUTs Findarr settings", async () => {
    const fetchSpy = mockFetch(jsonResponse({ running: false }))
    await updateFindarrSettings({ enabled: true })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/findarr/settings",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ enabled: true }),
      }),
    )
  })

  it("POSTs a manual run with the app", async () => {
    const fetchSpy = mockFetch(jsonResponse({ status: "completed" }))
    await runFindarr("sonarr")
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/findarr/run",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ app: "sonarr" }),
      }),
    )
  })

  it("POSTs a reset of processed state", async () => {
    const fetchSpy = mockFetch(jsonResponse({ status: "reset", removed: 0 }))
    await resetFindarrState()
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/findarr/reset",
      expect.objectContaining({ method: "POST" }),
    )
  })

  it("GETs the Findarr history", async () => {
    const fetchSpy = mockFetch(jsonResponse([]))
    await expect(getFindarrHistory()).resolves.toEqual([])
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/findarr/history",
      expect.anything(),
    )
  })

  it("POSTs a clear of the Findarr history", async () => {
    const fetchSpy = mockFetch(jsonResponse({ status: "cleared", removed: 3 }))
    await expect(clearFindarrHistory()).resolves.toEqual({
      status: "cleared",
      removed: 3,
    })
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/findarr/history/clear",
      expect.objectContaining({ method: "POST" }),
    )
  })
})
