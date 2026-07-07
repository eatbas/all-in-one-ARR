import { useState } from "react"
import { ActivityIcon, HistoryIcon, SettingsIcon } from "lucide-react"

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs"
import { History } from "@/features/findarr/tabs/History"
import { Settings } from "@/features/findarr/tabs/Settings"
import { Status } from "@/features/findarr/tabs/Status"
import {
  FINDARR_TAB_STORAGE_KEY,
  VALID_FINDARR_TABS,
} from "@/features/findarr/findarr-tab"

/** Findarr page: Sonarr/Radarr missing and upgrade searches. */
export function Findarr() {
  const [activeTab, setActiveTab] = useState(() => {
    if (typeof localStorage === "undefined") return "status"
    const stored = localStorage.getItem(FINDARR_TAB_STORAGE_KEY)
    return stored &&
      VALID_FINDARR_TABS.includes(stored as (typeof VALID_FINDARR_TABS)[number])
      ? stored
      : "status"
  })

  function handleTabChange(next: string) {
    setActiveTab(next)
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(FINDARR_TAB_STORAGE_KEY, next)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Findarr</h1>
        <p className="text-sm text-muted-foreground">
          Search missing and cutoff-unmet media in Sonarr 4+ and Radarr 6+.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="status">
            <ActivityIcon className="size-4" />
            Status
          </TabsTrigger>
          <TabsTrigger value="settings">
            <SettingsIcon className="size-4" />
            Settings
          </TabsTrigger>
          <TabsTrigger value="history">
            <HistoryIcon className="size-4" />
            History
          </TabsTrigger>
        </TabsList>
        <TabsContent value="status">
          <Status />
        </TabsContent>
        <TabsContent value="settings">
          <Settings />
        </TabsContent>
        <TabsContent value="history">
          <History />
        </TabsContent>
      </Tabs>
    </div>
  )
}
