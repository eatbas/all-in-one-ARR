import { useState } from "react"
import { FilmIcon, SettingsIcon, TvIcon } from "lucide-react"

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs"
import { Library } from "@/features/deletarr/tabs/Library"
import { Settings } from "@/features/deletarr/tabs/Settings"
import {
  DELETARR_TAB_STORAGE_KEY,
  VALID_DELETARR_TABS,
  type DeletarrTab,
} from "@/features/deletarr/deletarr-tab"

function storedTab(): DeletarrTab {
  if (typeof localStorage === "undefined") return "movies"
  const stored = localStorage.getItem(DELETARR_TAB_STORAGE_KEY)
  return stored && VALID_DELETARR_TABS.includes(stored as DeletarrTab)
    ? (stored as DeletarrTab)
    : "movies"
}

/** Deletarr page: review and delete junk and untracked-media candidates. */
export function Deletarr() {
  const [activeTab, setActiveTab] = useState<DeletarrTab>(storedTab)

  function handleTabChange(next: string) {
    /* v8 ignore next -- Radix only emits values from the rendered triggers. */
    if (!VALID_DELETARR_TABS.includes(next as DeletarrTab)) return
    const tab = next as DeletarrTab
    setActiveTab(tab)
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(DELETARR_TAB_STORAGE_KEY, tab)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Deletarr</h1>
        <p className="text-sm text-muted-foreground">
          Review junk files, empty folders, and untracked media in your
          libraries before deleting them.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="movies">
            <FilmIcon className="size-4" />
            Movies
          </TabsTrigger>
          <TabsTrigger value="tv">
            <TvIcon className="size-4" />
            TV Shows
          </TabsTrigger>
          <TabsTrigger value="settings">
            <SettingsIcon className="size-4" />
            Settings
          </TabsTrigger>
        </TabsList>
        <TabsContent value="movies">
          <Library type="movies" />
        </TabsContent>
        <TabsContent value="tv">
          <Library type="tv" />
        </TabsContent>
        <TabsContent value="settings">
          <Settings />
        </TabsContent>
      </Tabs>
    </div>
  )
}
