import { useState } from "react"

import { Button } from "@/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { Input } from "@/shared/components/ui/input"
import { Switch } from "@/shared/components/ui/switch"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs"
import {
  useAddTraktList,
  useRemoveTraktList,
  useTraktLists,
  useTraktSettings,
} from "@/shared/lib/queries"

/**
 * Reusable Trakt list selector: the "Add by Trakt URL" input sits at the top of
 * the card, followed by two sub-tabs — **Syncing** (the currently synced lists)
 * and **Your Trakt lists** (lists discovered on the connected Trakt account).
 * Used by the List-Syncarr settings tab so the selection UI stays consistent.
 */
export function TraktListSelector() {
  const { data: settings } = useTraktSettings()
  const connected = settings?.connected ?? false
  const lists = useTraktLists(connected)
  const add = useAddTraktList()
  const remove = useRemoveTraktList()
  const [url, setUrl] = useState("")

  function addByUrl() {
    add.mutate({ url })
    setUrl("")
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Lists</CardTitle>
        <CardDescription>
          Choose which Trakt lists to keep in sync (TV, Movies, Anime …).
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">Add by Trakt URL</p>
          <div className="flex gap-2">
            <Input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://trakt.tv/users/me/lists/anime"
            />
            <Button onClick={addByUrl} disabled={add.isPending || !url}>
              Add
            </Button>
          </div>
        </div>

        <Tabs defaultValue="syncing">
          <TabsList>
            <TabsTrigger value="syncing">Syncing</TabsTrigger>
            <TabsTrigger value="discovered">Your Trakt lists</TabsTrigger>
          </TabsList>
          <TabsContent value="syncing">
            <div className="flex flex-col gap-2">
              {(settings?.lists.length ?? 0) === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No lists selected yet.
                </p>
              ) : (
                <ul className="divide-y">
                  {settings?.lists.map((item) => (
                    <li
                      key={`${item.owner_user}:${item.slug}`}
                      className="flex items-center justify-between py-2"
                    >
                      <span className="text-sm">
                        <span className="font-medium">{item.name}</span>{" "}
                        <span className="text-muted-foreground">
                          ({item.owner_user}/{item.slug})
                        </span>
                      </span>
                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={() =>
                          remove.mutate({
                            owner_user: item.owner_user,
                            slug: item.slug,
                          })
                        }
                        disabled={remove.isPending}
                      >
                        Remove
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </TabsContent>
          <TabsContent value="discovered">
            <div className="flex flex-col gap-2">
              {!connected ? (
                <p className="text-sm text-muted-foreground">
                  Connect Trakt to discover your lists.
                </p>
              ) : lists.isLoading ? (
                <p className="text-sm text-muted-foreground">Loading lists…</p>
              ) : (lists.data?.length ?? 0) === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No lists found on your account.
                </p>
              ) : (
                <ul className="divide-y">
                  {lists.data?.map((entry) => (
                    <li
                      key={`${entry.owner_user}:${entry.slug}`}
                      className="flex items-center justify-between py-2"
                    >
                      <span className="text-sm">
                        <span className="font-medium">
                          {entry.name ?? entry.slug}
                        </span>{" "}
                        <span className="text-muted-foreground">
                          ({entry.item_count ?? 0} items)
                        </span>
                      </span>
                      <Switch
                        checked={entry.selected}
                        disabled={add.isPending || remove.isPending}
                        onCheckedChange={(checked) =>
                          checked
                            ? add.mutate({
                                owner_user: entry.owner_user,
                                slug: entry.slug,
                              })
                            : remove.mutate({
                                owner_user: entry.owner_user,
                                slug: entry.slug,
                              })
                        }
                        aria-label={`Sync ${entry.slug}`}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}
