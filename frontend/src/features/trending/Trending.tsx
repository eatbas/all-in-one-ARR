import { useState } from "react"

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs"
import {
  readStoredDensity,
  writeStoredDensity,
} from "@/shared/components/poster-grid/poster-grid-density"
import { readStoredItem, writeStoredItem } from "@/shared/lib/storage"
import {
  useServiceSettings,
  useTrending,
  useTrendingSearch,
  useTrendingStatus,
} from "@/shared/lib/queries"
import type {
  ItemType,
  TrendingCategory,
  TrendingQuery,
  TrendingSource,
} from "@/shared/lib/api"
import { isAvailable } from "@/features/trending/trending-item-status"
import { useDebouncedValue } from "@/features/trending/useDebouncedValue"
import { usePosterReveal } from "@/features/trending/usePosterReveal"
import { SourceToolbar } from "@/features/trending/components/SourceToolbar"
import { TrendingResultGrid } from "@/features/trending/components/TrendingResultGrid"
import { Toggle } from "@/features/trending/components/Toggle"
import {
  ANIME_SOURCES,
  DEFAULT_PER_ROW,
  SOURCE_LABELS,
  TAB_LABELS,
  TRENDING_ANIME_SOURCE_STORAGE_KEY,
  TRENDING_PER_ROW_STORAGE_KEY,
  TRENDING_SEARCH_DEBOUNCE_MS,
  TRENDING_SEARCH_MIN_LENGTH,
  TRENDING_TAB_STORAGE_KEY,
  VALID_TRENDING_TABS,
  type AnimeSource,
  type PerRow,
  type TrendingTab,
} from "@/features/trending/trending-tab"

/**
 * Status copy shown in place of the grid: the initial load, an empty result
 * set (search or feed), or a grid the hide-available filter emptied.
 */
function PanelStatusMessage({
  isInitialLoading,
  hasItems,
  isSearching,
  searchQuery,
  source,
}: {
  isInitialLoading: boolean
  /** Whether the active query returned any items (before the availability filter). */
  hasItems: boolean
  isSearching: boolean
  searchQuery: string
  source: TrendingSource
}) {
  let message: string
  if (isInitialLoading) {
    message = isSearching ? "Searching…" : "Loading trending…"
  } else if (!hasItems) {
    // AniList needs no credentials, so there is no connection to check.
    message = isSearching
      ? `No results for “${searchQuery}”.`
      : source === "anilist"
        ? "Nothing to show. AniList may be temporarily unavailable."
        : `Nothing to show. Check the ${SOURCE_LABELS[source]} connection in Settings.`
  } else {
    message =
      "Every result is already available. Turn off “Hide available” to see them."
  }
  return <p className="text-sm text-muted-foreground">{message}</p>
}

/**
 * Data toggles (media / category) and the search box on the left, display
 * options (per-row density / hide-available) on the right, then the grid. A
 * settled search query swaps the grid from the scheduled feed to live search
 * results from the same source. Results are revealed three rows at a time via
 * an infinite-scroll sentinel rather than paged.
 */
function SourcePanel({
  source,
  defaultMedia = "movie",
}: {
  source: TrendingSource
  /** Initial media toggle state; the Anime tab starts on shows. */
  defaultMedia?: ItemType
}) {
  const [media, setMedia] = useState<ItemType>(defaultMedia)
  const [category, setCategory] = useState<TrendingCategory>("trending")
  const [search, setSearch] = useState("")
  const [hideAvailable, setHideAvailable] = useState(false)
  const [perRow, setPerRow] = useState<PerRow>(() =>
    readStoredDensity(TRENDING_PER_ROW_STORAGE_KEY, DEFAULT_PER_ROW),
  )
  const searchQuery = useDebouncedValue(
    search,
    TRENDING_SEARCH_DEBOUNCE_MS,
  ).trim()
  const isSearching = searchQuery.length >= TRENDING_SEARCH_MIN_LENGTH
  const query: TrendingQuery = { source, media, category }
  const feed = useTrending(query)
  const searchState = useTrendingSearch(
    { source, media, query: searchQuery },
    isSearching,
  )
  // The grid renders whichever query is active; the feed stays cached in the
  // background so clearing the search restores it without a refetch flash.
  const active = isSearching ? searchState : feed
  const { data: services } = useServiceSettings()
  const { data: status } = useTrendingStatus()
  const seerUrl = services?.seer.url
  const items = active.data ?? []
  const isInitialLoading = active.isLoading && active.data === undefined

  // "Hide available" drops only titles the user can watch now (downloaded in
  // Radarr/Sonarr, or Available in Seer); requested/processing/missing items stay.
  const visible = hideAvailable
    ? items.filter((item) => !isAvailable(item))
    : items
  const total = visible.length

  const { visibleCount, hasMore, sentinelRef, resetReveal } = usePosterReveal(
    perRow,
    total,
  )
  const shown = visible.slice(0, visibleCount)

  function changeMedia(next: ItemType) {
    setMedia(next)
    resetReveal()
  }
  function changeCategory(next: TrendingCategory) {
    setCategory(next)
    resetReveal()
  }
  function changeSearch(next: string) {
    setSearch(next)
    // Reset on the keystroke, not the settled query: the outgoing grid is
    // about to be replaced, so collapsing it early is invisible in practice.
    resetReveal()
  }
  function changeHideAvailable(next: boolean) {
    setHideAvailable(next)
    resetReveal()
  }
  function changePerRow(next: PerRow) {
    setPerRow(next)
    // The batch follows the new density (not the current perRow), so the first
    // batch stays three rows even as the row width changes.
    resetReveal(next)
    writeStoredDensity(TRENDING_PER_ROW_STORAGE_KEY, next)
  }

  return (
    <div className="flex flex-col gap-4">
      <SourceToolbar
        media={media}
        category={category}
        search={search}
        hideAvailable={hideAvailable}
        perRow={perRow}
        isFetching={active.isFetching}
        isInitialLoading={isInitialLoading}
        lastSyncedAt={status?.last_synced_at}
        onChangeMedia={changeMedia}
        onChangeCategory={changeCategory}
        onChangeSearch={changeSearch}
        onChangeHideAvailable={changeHideAvailable}
        onChangePerRow={changePerRow}
      />

      {isInitialLoading || visible.length === 0 ? (
        <PanelStatusMessage
          isInitialLoading={isInitialLoading}
          hasItems={items.length > 0}
          isSearching={isSearching}
          searchQuery={searchQuery}
          source={source}
        />
      ) : (
        <TrendingResultGrid
          perRow={perRow}
          items={shown}
          seerUrl={seerUrl}
          sentinelRef={sentinelRef}
          hasMore={hasMore}
        />
      )}
    </div>
  )
}

function parseAnimeSource(raw: string): AnimeSource | undefined {
  return (ANIME_SOURCES as readonly string[]).includes(raw)
    ? (raw as AnimeSource)
    : undefined
}

/** Read the persisted anime sub-source, falling back to the first (AniList). */
function readStoredAnimeSource(): AnimeSource {
  return readStoredItem(
    TRENDING_ANIME_SOURCE_STORAGE_KEY,
    ANIME_SOURCES[0],
    parseAnimeSource,
  )
}

function writeStoredAnimeSource(value: AnimeSource): void {
  writeStoredItem(TRENDING_ANIME_SOURCE_STORAGE_KEY, value)
}

function parseTrendingTab(raw: string): TrendingTab | undefined {
  return VALID_TRENDING_TABS.includes(raw as TrendingTab)
    ? (raw as TrendingTab)
    : undefined
}

/** Read the persisted Trending page tab, falling back to Trakt. */
function readStoredTrendingTab(): TrendingTab {
  return readStoredItem(TRENDING_TAB_STORAGE_KEY, "trakt", parseTrendingTab)
}

function writeStoredTrendingTab(value: TrendingTab): void {
  writeStoredItem(TRENDING_TAB_STORAGE_KEY, value)
}

/**
 * Anime tab: a source toggle (AniList / Trakt / TMDB) above the shared source
 * panel. Anime is overwhelmingly episodic, so the panel defaults to shows.
 */
function AnimePanel() {
  const [source, setSource] = useState<AnimeSource>(readStoredAnimeSource)

  function changeSource(next: AnimeSource) {
    setSource(next)
    writeStoredAnimeSource(next)
  }

  return (
    <div className="flex flex-col gap-4">
      <Toggle
        ariaLabel="Anime source"
        value={source}
        onChange={changeSource}
        options={ANIME_SOURCES.map((value) => ({
          value,
          label: SOURCE_LABELS[value],
        }))}
      />
      {/* Keyed by source so switching also resets media/category state. */}
      <SourcePanel key={source} source={source} defaultMedia="show" />
    </div>
  )
}

/** Trending page: per-source (Trakt / TMDB / Seer / Anime) discovery with an add action. */
export function Trending() {
  const [activeTab, setActiveTab] = useState<string>(readStoredTrendingTab)

  function handleTabChange(next: string) {
    setActiveTab(next)
    writeStoredTrendingTab(next as TrendingTab)
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Trending</h1>
        <p className="text-sm text-muted-foreground">
          Trending and popular movies and shows from Trakt, TMDB and Seer, plus
          anime from AniList. Add any to one of your Trakt lists and it is
          synced and requested in Seer.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          {VALID_TRENDING_TABS.map((tab) => (
            <TabsTrigger key={tab} value={tab}>
              {TAB_LABELS[tab]}
            </TabsTrigger>
          ))}
        </TabsList>
        {VALID_TRENDING_TABS.map((tab) => (
          <TabsContent key={tab} value={tab}>
            {tab === "anime" ? <AnimePanel /> : <SourcePanel source={tab} />}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
