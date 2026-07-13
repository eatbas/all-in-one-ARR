import { PlusIcon } from "lucide-react"

import { Button } from "@/shared/components/ui/button"
import { PillLabel } from "@/shared/components/poster-pill/poster-pill"
import {
  pillIcon,
  pillIconSlot,
  pillShell,
  type PillDensity,
} from "@/shared/components/poster-pill/poster-pill-variants"
import { cn } from "@/shared/lib/utils"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu"
import { useAddTrending, useLists } from "@/shared/lib/queries"
import type { TrendingItem } from "@/shared/lib/api"

/**
 * Solid black add pill. The shared pill shell owns sizing so this control
 * matches the source and status controls in every density.
 */
function addButtonClasses(density: PillDensity): string {
  return cn(
    pillShell(density),
    "group/add gap-0 bg-black px-0 py-0 text-white hover:z-10 hover:bg-black/85 focus-visible:z-10 has-[>svg]:px-0",
  )
}

type AddButtonBodyProps = {
  density: PillDensity
}

/**
 * Shared body for both button variants: a bare "+" that expands to "Add +" on
 * hover or keyboard focus, reusing the shared poster-pill reveal so all three
 * corner pills animate the same way.
 */
function AddButtonBody({ density }: AddButtonBodyProps) {
  return (
    <>
      <PillLabel group="add" side="left" density={density}>
        Add
      </PillLabel>
      <span
        aria-hidden="true"
        className={pillIconSlot(density)}
        data-pill-icon-slot
      >
        <PlusIcon className={pillIcon(density)} />
      </span>
    </>
  )
}

/**
 * Add control for a trending card, rendered as a solid black "+" pill in the
 * poster's bottom-right corner that expands to "Add +" on hover: pick one of
 * the account's owned, syncable Trakt lists as the destination. Adding it
 * triggers the existing sync, which is what requests the item in Seer.
 * Disabled (with a hint) when the account has no owned, non-watchlist list to
 * add to.
 */
export function AddToListControl({
  item,
  density = 5,
}: {
  item: TrendingItem
  /** Posters-per-row density; controls pill and icon size. Defaults to the
   *  largest size for consumers that do not know the grid density. */
  density?: PillDensity
}) {
  const { data: lists } = useLists()
  const addTrending = useAddTrending()
  const ownedLists = (lists ?? []).filter(
    (list) => list.owner_user === "me" && list.slug !== "watchlist",
  )
  const buttonClasses = addButtonClasses(density)
  // Trakt resolves adds by id only; an item carrying none (an AniList title
  // Fribb's mapping does not cover yet) cannot be added.
  const hasUsableId =
    item.tmdb !== null ||
    item.imdb !== null ||
    item.tvdb !== null ||
    item.trakt !== null

  if (ownedLists.length === 0 || !hasUsableId) {
    return (
      <Button
        size="sm"
        disabled
        aria-label="Add to a list"
        title={
          hasUsableId
            ? "Add a personal Trakt list in Settings to enable adding"
            : "This title has no known Trakt/TMDB/TVDB/IMDb id yet, so it cannot be added"
        }
        className={buttonClasses}
      >
        <AddButtonBody density={density} />
      </Button>
    )
  }

  return (
    // Non-modal: the add menu needs neither scroll-lock nor focus-trap, so opt
    // out of react-remove-scroll entirely and keep the grid scrollable while
    // the menu is open. This is purely about interaction behaviour — the app
    // shell freezes the document (only <main> scrolls; see AppShell/index.css),
    // so a modal menu could not move the chrome anyway.
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          size="sm"
          disabled={addTrending.isPending}
          aria-label="Add to a list"
          title="Add to a Trakt list"
          className={buttonClasses}
        >
          <AddButtonBody density={density} />
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
