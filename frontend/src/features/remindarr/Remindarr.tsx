import { useState } from "react"
import { BellIcon, SettingsIcon } from "lucide-react"

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs"
import { Reminders } from "@/features/remindarr/tabs/Reminders"
import { Settings } from "@/features/remindarr/tabs/Settings"
import {
  REMINDARR_TAB_STORAGE_KEY,
  VALID_REMINDARR_TABS,
  type RemindarrTab,
} from "@/features/remindarr/remindarr-tab"

function storedTab(): RemindarrTab {
  if (typeof localStorage === "undefined") return "reminders"
  const stored = localStorage.getItem(REMINDARR_TAB_STORAGE_KEY)
  return stored && VALID_REMINDARR_TABS.includes(stored as RemindarrTab)
    ? (stored as RemindarrTab)
    : "reminders"
}

/** Remindarr page: unwatched downloaded episodes of tagged Sonarr series. */
export function Remindarr() {
  const [activeTab, setActiveTab] = useState<RemindarrTab>(storedTab)

  function handleTabChange(next: string) {
    /* v8 ignore next -- Radix only emits values from the rendered triggers. */
    if (!VALID_REMINDARR_TABS.includes(next as RemindarrTab)) return
    const tab = next as RemindarrTab
    setActiveTab(tab)
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(REMINDARR_TAB_STORAGE_KEY, tab)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Remindarr</h1>
        <p className="text-sm text-muted-foreground">
          Downloaded episodes you have not watched in Plex yet, from Sonarr
          series carrying your selected tags.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="reminders">
            <BellIcon className="size-4" />
            Reminders
          </TabsTrigger>
          <TabsTrigger value="settings">
            <SettingsIcon className="size-4" />
            Settings
          </TabsTrigger>
        </TabsList>
        <TabsContent value="reminders">
          <Reminders />
        </TabsContent>
        <TabsContent value="settings">
          <Settings />
        </TabsContent>
      </Tabs>
    </div>
  )
}
