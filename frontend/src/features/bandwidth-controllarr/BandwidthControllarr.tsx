import { useState } from "react"
import { ActivityIcon, SettingsIcon } from "lucide-react"

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs"
import { Status } from "@/features/bandwidth-controllarr/tabs/Status"
import { BandwidthSettings } from "@/features/bandwidth-controllarr/tabs/BandwidthSettings"
import {
  BANDWIDTH_CONTROLLARR_TAB_STORAGE_KEY,
  VALID_BANDWIDTH_CONTROLLARR_TABS,
} from "@/features/bandwidth-controllarr/bandwidth-controllarr-tab"

/**
 * Bandwidth-Controllarr page: a Status tab showing live client stats and a
 * Settings tab for the control switch and check interval. The active tab is
 * persisted to localStorage, mirroring the List-Syncarr page.
 */
export function BandwidthControllarr() {
  const [activeTab, setActiveTab] = useState(() => {
    if (typeof localStorage === "undefined") return "status"
    const stored = localStorage.getItem(BANDWIDTH_CONTROLLARR_TAB_STORAGE_KEY)
    return stored && VALID_BANDWIDTH_CONTROLLARR_TABS.includes(stored)
      ? stored
      : "status"
  })

  function handleTabChange(next: string) {
    setActiveTab(next)
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(BANDWIDTH_CONTROLLARR_TAB_STORAGE_KEY, next)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Bandwidth-Controllarr
        </h1>
        <p className="text-sm text-muted-foreground">
          Prioritise BitTorrent over Usenet by pausing SABnzbd while qBittorrent
          is active.
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
        </TabsList>
        <TabsContent value="status">
          <Status />
        </TabsContent>
        <TabsContent value="settings">
          <BandwidthSettings />
        </TabsContent>
      </Tabs>
    </div>
  )
}
