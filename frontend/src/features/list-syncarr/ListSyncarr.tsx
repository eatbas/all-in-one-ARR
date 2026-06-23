import { useState } from "react"
import { ListIcon, ListVideoIcon } from "lucide-react"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs"
import { Items } from "@/features/list-syncarr/tabs/Items"
import { Lists } from "@/features/list-syncarr/tabs/Lists"
import {
  LIST_SYNCARR_TAB_STORAGE_KEY,
  VALID_LIST_SYNCARR_TABS,
} from "@/features/list-syncarr/list-syncarr-tab"

/**
 * List-Syncarr page: the Trakt list-sync module surfaced as two tabs — **Lists**
 * (the Trakt lists kept in sync) and **Items** (their mirrored movies and shows).
 * The active tab is persisted to localStorage, mirroring the Settings page.
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
    <Tabs value={activeTab} onValueChange={handleTabChange}>
      <TabsList>
        <TabsTrigger value="lists">
          <ListIcon className="size-4" />
          Lists
        </TabsTrigger>
        <TabsTrigger value="items">
          <ListVideoIcon className="size-4" />
          Items
        </TabsTrigger>
      </TabsList>
      <TabsContent value="lists">
        <Lists />
      </TabsContent>
      <TabsContent value="items">
        <Items />
      </TabsContent>
    </Tabs>
  )
}
