import { PlusIcon } from "lucide-react"

import { Button } from "@/shared/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu"
import { useAddTrending, useLists } from "@/shared/lib/queries"
import type { TrendingItem } from "@/shared/lib/api"

/** Solid black "Add +" button so it reads as the primary action on the poster. */
const ADD_BUTTON = "bg-black text-white shadow-sm hover:bg-black/85"

/**
 * Add control for a trending card, rendered as a solid black "Add +" button in
 * the poster's bottom-right corner: pick one of the account's owned, syncable
 * Trakt lists as the destination. Adding it triggers the existing sync, which is
 * what requests the item in Seer. Disabled (with a hint) when the account has no
 * owned, non-watchlist list to add to.
 */
export function AddToListControl({ item }: { item: TrendingItem }) {
  const { data: lists } = useLists()
  const addTrending = useAddTrending()
  const ownedLists = (lists ?? []).filter(
    (list) => list.owner_user === "me" && list.slug !== "watchlist",
  )

  if (ownedLists.length === 0) {
    return (
      <Button
        size="sm"
        disabled
        aria-label="Add to a list"
        title="Add a personal Trakt list in Settings to enable adding"
        className={ADD_BUTTON}
      >
        Add
        <PlusIcon className="size-4" />
      </Button>
    )
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          size="sm"
          disabled={addTrending.isPending}
          aria-label="Add to a list"
          title="Add to a Trakt list"
          className={ADD_BUTTON}
        >
          Add
          <PlusIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>Add to list</DropdownMenuLabel>
        {ownedLists.map((list) => (
          <DropdownMenuItem
            key={`${list.owner_user}:${list.slug}`}
            onSelect={() =>
              addTrending.mutate({
                media_type: item.media_type,
                owner_user: list.owner_user,
                slug: list.slug,
                tmdb: item.tmdb,
                imdb: item.imdb,
                trakt: item.trakt,
                tvdb: item.tvdb,
                title: item.title,
              })
            }
          >
            {list.name}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
