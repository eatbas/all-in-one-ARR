import { Trash2Icon } from "lucide-react"

import {
  ResultGroupPanel,
  type ResultGroup,
} from "@/features/deletarr/components/result-group-panel"
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
import type { DeletarrScanItem } from "@/shared/lib/api"
import { formatBytes } from "@/shared/lib/format"

interface ResultSectionProps {
  description: string
  groups: ResultGroup[]
  items: DeletarrScanItem[]
  selectAllLabel: string
  selectedSet: Set<string>
  title: string
  onItemSelection: (path: string, checked: boolean) => void
  onItemsSelection: (items: DeletarrScanItem[], checked: boolean) => void
}

function ResultSection({
  description,
  groups,
  items,
  selectAllLabel,
  selectedSet,
  title,
  onItemSelection,
  onItemsSelection,
}: ResultSectionProps) {
  const selectedCount = items.filter((item) =>
    selectedSet.has(item.path),
  ).length
  const allSelected = selectedCount === items.length
  const partiallySelected = selectedCount > 0 && !allSelected

  return (
    <section className="flex flex-col gap-3" aria-label={title}>
      <div className="flex flex-col gap-3 rounded-lg border bg-muted/30 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold">
            {title} ({items.length})
          </h3>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={allSelected}
            ref={(element) => {
              if (element) element.indeterminate = partiallySelected
            }}
            onChange={(event) => onItemsSelection(items, event.target.checked)}
          />
          {selectAllLabel}
        </label>
      </div>
      {groups.map((group) => (
        <ResultGroupPanel
          key={group.key}
          group={group}
          selectedSet={selectedSet}
          onGroupSelection={(selectedGroup, checked) =>
            onItemsSelection(selectedGroup.items, checked)
          }
          onItemSelection={onItemSelection}
        />
      ))}
    </section>
  )
}

interface ResultsSummaryProps {
  isDeleting: boolean
  label: string
  selectedCount: number
  selectedSize: number
  totalCount: number
  onDelete: () => void
}

function ResultsSummary({
  isDeleting,
  label,
  selectedCount,
  selectedSize,
  totalCount,
  onDelete,
}: ResultsSummaryProps) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-background p-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h2 className="text-base font-semibold">Scan results</h2>
        <p className="text-sm text-muted-foreground">
          {selectedCount} of {totalCount} candidate(s) selected.
        </p>
      </div>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button
            type="button"
            variant="destructive"
            disabled={selectedCount === 0 || isDeleting}
          >
            <Trash2Icon className="size-4" />
            Delete selected
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete selected Deletarr items?</AlertDialogTitle>
            <AlertDialogDescription>
              This will delete {selectedCount} current scan result(s) from the{" "}
              {label.toLowerCase()} library and reclaim about{" "}
              {formatBytes(selectedSize)}.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={onDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

interface LibraryResultsProps {
  arrLabel: string
  isDeleting: boolean
  isLoading: boolean
  items: DeletarrScanItem[]
  junkGroups: ResultGroup[]
  junkItems: DeletarrScanItem[]
  label: string
  selectedPaths: string[]
  selectedSet: Set<string>
  selectedSize: number
  untrackedGroups: ResultGroup[]
  untrackedItems: DeletarrScanItem[]
  onDelete: () => void
  onItemSelection: (path: string, checked: boolean) => void
  onItemsSelection: (items: DeletarrScanItem[], checked: boolean) => void
}

/** Present destructive selection, confirmation, and grouped candidates. */
export function LibraryResults(props: LibraryResultsProps) {
  const hasResults = props.junkGroups.length + props.untrackedGroups.length > 0
  return (
    <>
      <ResultsSummary
        isDeleting={props.isDeleting}
        label={props.label}
        selectedCount={props.selectedPaths.length}
        selectedSize={props.selectedSize}
        totalCount={props.items.length}
        onDelete={props.onDelete}
      />
      {props.isLoading ? (
        <p className="rounded-lg border bg-background p-4 text-sm text-muted-foreground">
          Loading Deletarr results...
        </p>
      ) : !hasResults ? (
        <p className="rounded-lg border bg-background p-4 text-sm text-muted-foreground">
          No review candidates found for {props.label.toLowerCase()}.
        </p>
      ) : (
        <div className="flex flex-col gap-5">
          {props.junkItems.length > 0 ? (
            <ResultSection
              title="Junk files and folders"
              description="Review sidecars, duplicates, misplaced media, and empty folders."
              selectAllLabel="Select all junk"
              items={props.junkItems}
              groups={props.junkGroups}
              selectedSet={props.selectedSet}
              onItemsSelection={props.onItemsSelection}
              onItemSelection={props.onItemSelection}
            />
          ) : null}
          {props.untrackedItems.length > 0 ? (
            <ResultSection
              title="Untracked media"
              description={`Whole folders, videos, and loose files ${props.arrLabel} does not track.`}
              selectAllLabel="Select all untracked media"
              items={props.untrackedItems}
              groups={props.untrackedGroups}
              selectedSet={props.selectedSet}
              onItemsSelection={props.onItemsSelection}
              onItemSelection={props.onItemSelection}
            />
          ) : null}
        </div>
      )}
    </>
  )
}
