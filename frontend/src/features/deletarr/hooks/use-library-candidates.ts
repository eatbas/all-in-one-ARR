import { useMemo } from "react"

import { useCandidateSelection } from "@/features/deletarr/hooks/use-candidate-selection"
import { groupResults } from "@/features/deletarr/result-groups"
import type { DeletarrLibraryType, DeletarrScanItem } from "@/shared/lib/api"

function candidateSignature(
  type: DeletarrLibraryType,
  currentPath: string,
  items: DeletarrScanItem[],
): string {
  return `${type}:${currentPath}:${items
    .map((item) => item.path)
    .sort()
    .join("\u0000")}`
}

/** Derive categorised result groups and selection for one library result set. */
export function useLibraryCandidates(
  type: DeletarrLibraryType,
  currentPath: string,
  items: DeletarrScanItem[],
  isScanning: boolean,
) {
  const junkItems = useMemo(
    () => items.filter((item) => item.category === "junk"),
    [items],
  )
  const untrackedItems = useMemo(
    () => items.filter((item) => item.category === "untracked_media"),
    [items],
  )
  const selectionKey = useMemo(
    () => candidateSignature(type, currentPath, items),
    [currentPath, items, type],
  )
  const selection = useCandidateSelection(selectionKey, isScanning)
  return {
    junkGroups: useMemo(() => groupResults(junkItems), [junkItems]),
    junkItems,
    selectedSize: items.reduce(
      (total, item) =>
        selection.selectedSet.has(item.path) ? total + item.size : total,
      0,
    ),
    selection,
    untrackedGroups: useMemo(
      () => groupResults(untrackedItems),
      [untrackedItems],
    ),
    untrackedItems,
  }
}
