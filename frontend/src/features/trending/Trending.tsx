import { useState } from "react"

import { Button } from "@/shared/components/ui/button"
import { Switch } from "@/shared/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs"
import { useServiceSettings, useTrending } from "@/shared/lib/queries"
import type {
  ItemType,
  TrendingCategory,
  TrendingQuery,
  TrendingSource,
} from "@/shared/lib/api"
import { TrendingCard } from "@/features/trending/components/TrendingCard"
import {
  SOURCE_LABELS,
  TRENDING_TAB_STORAGE_KEY,
  VALID_TRENDING_TABS,
  type TrendingTab,
} from "@/features/trending/trending-tab"

/** Seer mediaInfo status meaning the title is already available in the library. */
const SEER_AVAILABLE_STATUS = 5

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

/** Controls (media / category / hide-available) and the grid for one source. */
function SourcePanel({ source }: { source: TrendingSource }) {
  const [media, setMedia] = useState<ItemType>("movie")
  const [category, setCategory] = useState<TrendingCategory>("trending")
  const [hideAvailable, setHideAvailable] = useState(false)
  const query: TrendingQuery = { source, media, category }
  const { data, isLoading } = useTrending(query)
  const { data: services } = useServiceSettings()
  const seerUrl = services?.seer.url
  const items = data ?? []
  // "Hide available" drops titles the user already has: in Radarr/Sonarr
  // (in_library) or reported available in Seer.
  const visible = hideAvailable
    ? items.filter(
        (item) =>
          !item.in_library && item.seer_status !== SEER_AVAILABLE_STATUS,
      )
    : items

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Toggle
          ariaLabel="Media type"
          value={media}
          onChange={setMedia}
          options={[
            { value: "movie", label: "Movies" },
            { value: "show", label: "Shows" },
          ]}
        />
        <Toggle
          ariaLabel="Category"
          value={category}
          onChange={setCategory}
          options={[
            { value: "trending", label: "Trending" },
            { value: "popular", label: "Popular" },
          ]}
        />
        <div className="ml-auto flex items-center gap-2">
          <Switch
            aria-label="Hide available items"
            checked={hideAvailable}
            onCheckedChange={setHideAvailable}
          />
          <span className="text-sm text-muted-foreground">Hide available</span>
        </div>
      </div>

      {isLoading ? (
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
        <ul className="grid grid-cols-3 gap-4 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6">
          {visible.map((item, index) => (
            <TrendingCard
              // The index keeps the key unique even if two items share a tmdb/title.
              key={`${item.source}:${item.media_type}:${item.tmdb ?? item.title}:${index}`}
              item={item}
              seerUrl={seerUrl}
            />
          ))}
        </ul>
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
          Trending and popular movies and shows from Trakt, TMDB and Seer. Add any
          to one of your Trakt lists and it is synced and requested in Seer.
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
