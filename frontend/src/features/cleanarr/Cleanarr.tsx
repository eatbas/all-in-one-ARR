import { useState } from "react"
import { ActivityIcon, HistoryIcon, ListIcon, SettingsIcon } from "lucide-react"

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs"
import { History } from "@/features/cleanarr/tabs/History"
import { Queue } from "@/features/cleanarr/tabs/Queue"
import { Settings } from "@/features/cleanarr/tabs/Settings"
import { Status } from "@/features/cleanarr/tabs/Status"
import {
  CLEANARR_TAB_STORAGE_KEY,
  VALID_CLEANARR_TABS,
} from "@/features/cleanarr/cleanarr-tab"

/** Cleanarr page: stuck Sonarr/Radarr usenet downloads and SABnzbd tidying. */
export function Cleanarr() {
  const [activeTab, setActiveTab] = useState(() => {
    if (typeof localStorage === "undefined") return "status"
    const stored = localStorage.getItem(CLEANARR_TAB_STORAGE_KEY)
    return stored &&
      VALID_CLEANARR_TABS.includes(
        stored as (typeof VALID_CLEANARR_TABS)[number],
      )
      ? stored
      : "status"
  })

  function handleTabChange(next: string) {
    setActiveTab(next)
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(CLEANARR_TAB_STORAGE_KEY, next)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Cleanarr</h1>
        <p className="text-sm text-muted-foreground">
          Clear stuck and failed downloads from Sonarr/Radarr queues and tidy
          SABnzbd&apos;s completed folder.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="status">
            <ActivityIcon className="size-4" />
            Status
          </TabsTrigger>
          <TabsTrigger value="queue">
            <ListIcon className="size-4" />
            Queue
          </TabsTrigger>
          <TabsTrigger value="history">
            <HistoryIcon className="size-4" />
            History
          </TabsTrigger>
          <TabsTrigger value="settings">
            <SettingsIcon className="size-4" />
            Settings
          </TabsTrigger>
        </TabsList>
        <TabsContent value="status">
          <Status />
        </TabsContent>
        <TabsContent value="queue">
          <Queue />
        </TabsContent>
        <TabsContent value="history">
          <History />
        </TabsContent>
        <TabsContent value="settings">
          <Settings />
        </TabsContent>
      </Tabs>
    </div>
  )
}
