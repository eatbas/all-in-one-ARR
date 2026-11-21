import { describe, expect, it } from "vitest"

import {
  ANIME_SOURCES,
  GENRE_FILTER_LABELS,
  GENRE_FILTERS,
  SOURCE_LABELS,
  isGenreFilterable,
  resolveTrendingSource,
} from "@/features/trending/trending-tab"

describe("genre filter helpers", () => {
  it("offers All then Animation, with All as the default", () => {
    expect(GENRE_FILTERS).toEqual(["all", "animation"])
    expect(GENRE_FILTERS.map((value) => GENRE_FILTER_LABELS[value])).toEqual([
      "All",
      "Animation",
    ])
  })

  it("treats only the Trakt, TMDB and Seer base sources as filterable", () => {
    expect(isGenreFilterable("trakt")).toBe(true)
    expect(isGenreFilterable("tmdb")).toBe(true)
    expect(isGenreFilterable("seer")).toBe(true)
    for (const source of ANIME_SOURCES) {
      expect(isGenreFilterable(source)).toBe(false)
    }
    // A variant is never filterable again.
    expect(isGenreFilterable("tmdb-animation")).toBe(false)
  })

  it("resolves Animation to the base source's variant", () => {
    expect(resolveTrendingSource("trakt", "animation")).toBe("trakt-animation")
    expect(resolveTrendingSource("tmdb", "animation")).toBe("tmdb-animation")
    expect(resolveTrendingSource("seer", "animation")).toBe("seer-animation")
  })

  it("leaves the source unchanged for All or a non-filterable source", () => {
    expect(resolveTrendingSource("trakt", "all")).toBe("trakt")
    expect(resolveTrendingSource("anilist", "animation")).toBe("anilist")
    expect(resolveTrendingSource("tmdb-anime", "animation")).toBe("tmdb-anime")
  })

  it("labels each Animation variant with its base provider", () => {
    expect(SOURCE_LABELS["trakt-animation"]).toBe("Trakt")
    expect(SOURCE_LABELS["tmdb-animation"]).toBe("TMDB")
    expect(SOURCE_LABELS["seer-animation"]).toBe("Seer")
  })
})
