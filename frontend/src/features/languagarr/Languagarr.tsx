import { useState } from "react"
import { AudioLinesIcon, ListOrderedIcon, SettingsIcon } from "lucide-react"

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs"
import { Queue } from "@/features/languagarr/tabs/Queue"
import { Review } from "@/features/languagarr/tabs/Review"
import { Settings } from "@/features/languagarr/tabs/Settings"
import {
  LANGUAGARR_TAB_STORAGE_KEY,
  VALID_LANGUAGARR_TABS,
  type LanguagarrTab,
} from "@/features/languagarr/languagarr-tab"

function storedTab(): LanguagarrTab {
  if (typeof localStorage === "undefined") return "review"
  const stored = localStorage.getItem(LANGUAGARR_TAB_STORAGE_KEY)
  return stored && VALID_LANGUAGARR_TABS.includes(stored as LanguagarrTab)
    ? (stored as LanguagarrTab)
    : "review"
}

/** Languagarr page: keep Sonarr anime on English dual audio. */
export function Languagarr() {
  const [activeTab, setActiveTab] = useState<LanguagarrTab>(storedTab)

  function handleTabChange(next: string) {
    /* v8 ignore next -- Radix only emits values from the rendered triggers. */
    if (!VALID_LANGUAGARR_TABS.includes(next as LanguagarrTab)) return
    const tab = next as LanguagarrTab
    setActiveTab(tab)
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(LANGUAGARR_TAB_STORAGE_KEY, tab)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Languagarr</h1>
        <p className="text-sm text-muted-foreground">
          Find Sonarr anime episodes without English dual audio and replace
          them.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="review">
            <AudioLinesIcon className="size-4" />
            Review
          </TabsTrigger>
          <TabsTrigger value="queue">
            <ListOrderedIcon className="size-4" />
            Queue
          </TabsTrigger>
          <TabsTrigger value="settings">
            <SettingsIcon className="size-4" />
            Settings
          </TabsTrigger>
        </TabsList>
        <TabsContent value="review">
          <Review />
        </TabsContent>
        <TabsContent value="queue">
          <Queue />
        </TabsContent>
        <TabsContent value="settings">
          <Settings />
        </TabsContent>
      </Tabs>
    </div>
  )
}
