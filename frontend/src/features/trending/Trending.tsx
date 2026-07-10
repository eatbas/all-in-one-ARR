import { useEffect, useRef, useState } from "react"
import { LayoutGridIcon } from "lucide-react"

import { Button } from "@/shared/components/ui/button"
import { Slider } from "@/shared/components/ui/slider"
import { Switch } from "@/shared/components/ui/switch"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs"
import { formatRelativeTime } from "@/shared/lib/format"
import {
  useServiceSettings,
  useTrending,
  useTrendingStatus,
} from "@/shared/lib/queries"
import type {
  ItemType,
  TrendingCategory,
  TrendingQuery,
  TrendingSource,
} from "@/shared/lib/api"
import { TrendingCard } from "@/features/trending/components/TrendingCard"
import { isAvailable } from "@/features/trending/trending-item-status"
import {
  SOURCE_LABELS,
  TRENDING_PER_ROW_STORAGE_KEY,
  TRENDING_TAB_STORAGE_KEY,
  VALID_PER_ROW_VALUES,
  VALID_TRENDING_TABS,
  type PerRow,
  type TrendingTab,
} from "@/features/trending/trending-tab"

/** Rows revealed per infinite-scroll batch — also the initial number of rows. */
const ROWS_PER_BATCH = 3

/**
 * Grid column classes per posters-per-row density. The selector varies only the
 * large-screen count; base/sm/md stay responsive so narrow viewports are not crammed.
 * Full literal class strings — Tailwind JIT does not compile interpolated names.
 */
const GRID_COLS: Record<PerRow, string> = {
  5: "grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5",
  6: "grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6",
  7: "grid grid-cols-3 gap-4 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-7",
  8: "grid grid-cols-3 gap-4 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8",
  9: "grid grid-cols-3 gap-4 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-9",
  10: "grid grid-cols-4 gap-4 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-10",
  11: "grid grid-cols-4 gap-4 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-11",
}

/** Read the persisted per-row density, falling back to the first valid value. */
function readStoredPerRow(): PerRow {
  if (typeof localStorage === "undefined") return VALID_PER_ROW_VALUES[0]
  const stored = Number(localStorage.getItem(TRENDING_PER_ROW_STORAGE_KEY))
  return (VALID_PER_ROW_VALUES as readonly number[]).includes(stored)
    ? (stored as PerRow)
    : VALID_PER_ROW_VALUES[0]
}

/** A small two/three-option segmented toggle rendered as a button group. */
function Toggle<T extends string>({
  ariaLabel,
  value,
  options,
  onChange,
}: {
  ariaLabel: string
  value: T
  options: ReadonlyArray<{ value: T; label: string }>
  onChange: (value: T) => void
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="inline-flex items-center gap-0.5 rounded-md border p-0.5"
    >
      {options.map((option) => (
        <Button
          key={option.value}
          type="button"
          size="sm"
          variant={value === option.value ? "default" : "ghost"}
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </Button>
      ))}
    </div>
  )
}

/**
 * Data toggles (media / category) on the left, display options (per-row
 * density / hide-available) on the right, then the grid. Results are revealed
 * {@link ROWS_PER_BATCH} rows at a time via an infinite-scroll sentinel rather
 * than paged.
 */
function SourcePanel({ source }: { source: TrendingSource }) {
  const [media, setMedia] = useState<ItemType>("movie")
  const [category, setCategory] = useState<TrendingCategory>("trending")
  const [hideAvailable, setHideAvailable] = useState(false)
  const [perRow, setPerRow] = useState<PerRow>(readStoredPerRow)
  const [visibleCount, setVisibleCount] = useState(
    () => ROWS_PER_BATCH * perRow,
  )
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  const query: TrendingQuery = { source, media, category }
  const { data, isFetching, isLoading } = useTrending(query)
  const { data: services } = useServiceSettings()
  const { data: status } = useTrendingStatus()
  const seerUrl = services?.seer.url
  const items = data ?? []
  const isInitialLoading = isLoading && data === undefined

  // Collapse the infinite-scroll reveal to the first batch (three rows). Any
  // control that changes which/how-many items are shown calls this, so a filter
  // change never leaves a long list expanded.
  function resetReveal() {
    setVisibleCount(ROWS_PER_BATCH * perRow)
  }
  function changeMedia(next: ItemType) {
    setMedia(next)
    resetReveal()
  }
  function changeCategory(next: TrendingCategory) {
    setCategory(next)
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
    setVisibleCount(ROWS_PER_BATCH * next)
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(TRENDING_PER_ROW_STORAGE_KEY, String(next))
    }
  }

  // "Hide available" drops only titles the user can watch now (downloaded in
  // Radarr/Sonarr, or Available in Seer); requested/processing/missing items stay.
  const visible = hideAvailable
    ? items.filter((item) => !isAvailable(item))
    : items

  const total = visible.length
  const shown = visible.slice(0, visibleCount)
  const hasMore = visibleCount < total

  // Reveal the next batch when the sentinel scrolls into view. Re-subscribing on
  // visibleCount means a sentinel still in view after a reveal (viewport taller
  // than the batch) keeps loading until it is pushed off-screen or the list ends;
  // Math.min and the hasMore guard bound the growth to the fetched list.
  useEffect(() => {
    if (visibleCount >= total) return
    const node = sentinelRef.current
    if (!node) return
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) {
        setVisibleCount((count) =>
          Math.min(count + ROWS_PER_BATCH * perRow, total),
        )
      }
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [perRow, total, visibleCount])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Toggle
          ariaLabel="Media type"
          value={media}
          onChange={changeMedia}
          options={[
            { value: "movie", label: "Movies" },
            { value: "show", label: "Shows" },
          ]}
        />
        <Toggle
          ariaLabel="Category"
          value={category}
          onChange={changeCategory}
          options={[
            { value: "trending", label: "Trending" },
            { value: "popular", label: "Popular" },
          ]}
        />
        <div className="ml-auto flex items-center gap-3">
          {isFetching && !isInitialLoading ? (
            <span className="text-xs text-muted-foreground">Refreshing</span>
          ) : null}
          {status?.last_synced_at ? (
            <span className="text-xs text-muted-foreground">
              Updated {formatRelativeTime(status.last_synced_at)}
            </span>
          ) : null}
          {/* Posters-per-row density slider; the numeric read-out echoes the
              current value so the bare grid icon is not the only cue. `min`/`max`
              are the ends of VALID_PER_ROW_VALUES and `step={1}` walks it, which
              assumes that allow-list stays contiguous (see trending-tab.ts). */}
          <div className="flex items-center gap-2" title="Posters per row">
            <LayoutGridIcon
              aria-hidden="true"
              className="size-4 text-muted-foreground"
            />
            <Slider
              aria-label="Posters per row"
              className="w-28"
              min={VALID_PER_ROW_VALUES[0]}
              max={VALID_PER_ROW_VALUES[VALID_PER_ROW_VALUES.length - 1]}
              step={1}
              value={[perRow]}
              onValueChange={([next]) => changePerRow(next as PerRow)}
            />
            <span className="w-4 text-sm tabular-nums text-muted-foreground">
              {perRow}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Switch
              aria-label="Hide available items"
              checked={hideAvailable}
              onCheckedChange={changeHideAvailable}
            />
            <span className="text-sm text-muted-foreground">
              Hide available
            </span>
          </div>
        </div>
      </div>

      {isInitialLoading ? (
        <p className="text-sm text-muted-foreground">Loading trending…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nothing to show. Check the {SOURCE_LABELS[source]} connection in
          Settings.
        </p>
      ) : visible.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Every result is already available. Turn off “Hide available” to see
          them.
        </p>
      ) : (
        <>
          <ul className={GRID_COLS[perRow]}>
            {shown.map((item, index) => (
              <TrendingCard
                // The index keeps the key unique even if two items share a tmdb/title.
                key={`${item.source}:${item.media_type}:${item.tmdb ?? item.title}:${index}`}
                item={item}
                seerUrl={seerUrl}
                density={perRow}
              />
            ))}
          </ul>
          {hasMore ? (
            <div
              ref={sentinelRef}
              aria-hidden="true"
              className="h-8"
              data-testid="trending-scroll-sentinel"
            />
          ) : null}
        </>
      )}
    </div>
  )
}

/** Trending page: per-source (Trakt / TMDB / Seer) discovery with an add action. */
export function Trending() {
  const [activeTab, setActiveTab] = useState<string>(() => {
    if (typeof localStorage === "undefined") return "trakt"
    const stored = localStorage.getItem(TRENDING_TAB_STORAGE_KEY)
    return stored && VALID_TRENDING_TABS.includes(stored as TrendingTab)
      ? stored
      : "trakt"
  })

  function handleTabChange(next: string) {
    setActiveTab(next)
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(TRENDING_TAB_STORAGE_KEY, next)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Trending</h1>
        <p className="text-sm text-muted-foreground">
          Trending and popular movies and shows from Trakt, TMDB and Seer. Add
          any to one of your Trakt lists and it is synced and requested in Seer.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          {VALID_TRENDING_TABS.map((source) => (
            <TabsTrigger key={source} value={source}>
              {SOURCE_LABELS[source]}
            </TabsTrigger>
          ))}
        </TabsList>
        {VALID_TRENDING_TABS.map((source) => (
          <TabsContent key={source} value={source}>
            <SourcePanel source={source} />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
