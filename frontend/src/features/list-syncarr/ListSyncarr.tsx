import { useState } from "react"
import { ListIcon, SettingsIcon } from "lucide-react"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs"
import { Lists } from "@/features/list-syncarr/tabs/Lists"
import { ListSettings } from "@/features/list-syncarr/tabs/ListSettings"
import {
  LIST_SYNCARR_TAB_STORAGE_KEY,
  VALID_LIST_SYNCARR_TABS,
} from "@/features/list-syncarr/list-syncarr-tab"

/**
 * List-Syncarr page: a header above two tabs — **Lists** (the Trakt lists kept in
 * sync, with their mirrored movies and shows and the sync-engine stat cards) and
 * **Settings** (choosing which Trakt lists to sync). The active tab is persisted to
 * localStorage, mirroring the Settings page.
 */
export function ListSyncarr() {
  const [activeTab, setActiveTab] = useState(() => {
    if (typeof localStorage === "undefined") return "lists"
    const stored = localStorage.getItem(LIST_SYNCARR_TAB_STORAGE_KEY)
    return stored && VALID_LIST_SYNCARR_TABS.includes(stored) ? stored : "lists"
  })

  function handleTabChange(next: string) {
    setActiveTab(next)
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(LIST_SYNCARR_TAB_STORAGE_KEY, next)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">List-Syncarr</h1>
        <p className="text-sm text-muted-foreground">
          Mirror your Trakt lists to Seer and track what&apos;s synced,
          requested, available, and removed.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="lists">
            <ListIcon className="size-4" />
            Lists
          </TabsTrigger>
          <TabsTrigger value="settings">
            <SettingsIcon className="size-4" />
            Settings
          </TabsTrigger>
        </TabsList>
        <TabsContent value="lists">
          <Lists />
        </TabsContent>
        <TabsContent value="settings">
          <ListSettings />
        </TabsContent>
      </Tabs>
    </div>
  )
}
