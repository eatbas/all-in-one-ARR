import { RefreshCwIcon, Trash2Icon } from "lucide-react"

import { PosterDensityControl } from "@/shared/components/poster-grid/poster-grid-density-control"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/components/ui/alert-dialog"
import { Button } from "@/shared/components/ui/button"
import { Switch } from "@/shared/components/ui/switch"
import { cn } from "@/shared/lib/utils"
import type { PosterDensity } from "@/shared/components/poster-grid/poster-grid-density"

interface ListsToolbarProps {
  density: PosterDensity
  showRemoved: boolean
  syncPending: boolean
  removeAvailablePending: boolean
  onDensityChange: (density: PosterDensity) => void
  onShowRemovedChange: (show: boolean) => void
  onSync: () => void
  onRemoveAvailable: () => void
}

/** Action toolbar inside the Synced lists card header. */
export function ListsToolbar({
  density,
  showRemoved,
  syncPending,
  removeAvailablePending,
  onDensityChange,
  onShowRemovedChange,
  onSync,
  onRemoveAvailable,
}: ListsToolbarProps) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-4 sm:w-auto w-full">
      <Button size="sm" onClick={onSync} disabled={syncPending}>
        {/* The icon spins while a sync is in flight so the disabled state
            reads as "working" rather than simply inert. */}
        <RefreshCwIcon
          className={cn("size-4", syncPending && "animate-spin")}
        />
        Sync now
      </Button>
      <div className="flex items-center gap-2">
        <Switch
          aria-label="Show removed items"
          checked={showRemoved}
          onCheckedChange={onShowRemovedChange}
        />
        <span className="text-sm text-muted-foreground">Show removed</span>
      </div>
      <PosterDensityControl value={density} onChange={onDensityChange} />
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="outline" size="sm" disabled={removeAvailablePending}>
            <Trash2Icon className="size-4" />
            Delete availables
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete available items?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes every item Seer reports as available from its Trakt
              list.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={onRemoveAvailable}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
