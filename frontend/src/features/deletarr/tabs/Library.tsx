import { useMemo } from "react"

import { LibraryResults } from "@/features/deletarr/components/library-results"
import { LibraryScanPanel } from "@/features/deletarr/components/library-scan-panel"
import { useLibraryCandidates } from "@/features/deletarr/hooks/use-library-candidates"
import type { DeletarrLibraryType } from "@/shared/lib/api"
import {
  useDeleteDeletarrItems,
  useDeletarrResults,
  useDeletarrStatus,
  useScanDeletarr,
} from "@/shared/lib/queries"

const LIBRARY_LABELS: Record<DeletarrLibraryType, string> = {
  movies: "Movies",
  tv: "TV Shows",
}

const ARR_LABELS: Record<DeletarrLibraryType, string> = {
  movies: "Radarr",
  tv: "Sonarr",
}

const LIBRARY_PATH_KEYS: Record<
  DeletarrLibraryType,
  "movies_path" | "tv_path"
> = {
  movies: "movies_path",
  tv: "tv_path",
}

interface LibraryProps {
  type: DeletarrLibraryType
}

/** Deletarr scan/delete tab orchestrator for one media library. */
export function Library({ type }: LibraryProps) {
  const statusQuery = useDeletarrStatus()
  const resultsQuery = useDeletarrResults(type)
  const scanLibrary = useScanDeletarr()
  const deleteItems = useDeleteDeletarrItems()
  const status = statusQuery.data?.libraries[type]
  const results = resultsQuery.data
  const settingsPath = statusQuery.data?.settings[LIBRARY_PATH_KEYS[type]]
  const currentPath = results?.path ?? status?.path ?? settingsPath ?? ""
  const items = useMemo(() => results?.results ?? [], [results?.results])
  const isScanning = Boolean(
    status?.stats.is_scanning || results?.stats.is_scanning,
  )
  const candidates = useLibraryCandidates(type, currentPath, items, isScanning)

  function handleScan() {
    candidates.selection.reset()
    scanLibrary.mutate(type)
  }

  function handleDelete() {
    deleteItems.mutate(
      { type, paths: candidates.selection.selectedPaths },
      { onSuccess: candidates.selection.reset },
    )
  }

  const stats = results?.stats ?? status?.stats
  const label = LIBRARY_LABELS[type]
  const arrLabel = ARR_LABELS[type]
  return (
    <div className="flex flex-col gap-4">
      <LibraryScanPanel
        arrDetail={status?.arr_detail ?? results?.arr_detail ?? null}
        arrLabel={arrLabel}
        arrSourceEnabled={statusQuery.data?.settings.use_arr_source ?? true}
        currentPath={currentPath}
        isBusy={isScanning || scanLibrary.isPending || deleteItems.isPending}
        isScanning={isScanning}
        label={label}
        lastError={status?.last_error}
        lastScanAt={status?.last_scan_at}
        scanMode={results?.scan_mode ?? status?.scan_mode ?? "heuristic"}
        totalFiles={stats?.total_files ?? 0}
        totalFolders={stats?.total_folders ?? 0}
        totalSize={stats?.total_size ?? 0}
        onScan={handleScan}
      />
      <LibraryResults
        arrLabel={arrLabel}
        isDeleting={deleteItems.isPending}
        isLoading={resultsQuery.isLoading}
        items={items}
        junkGroups={candidates.junkGroups}
        junkItems={candidates.junkItems}
        label={label}
        selectedPaths={candidates.selection.selectedPaths}
        selectedSet={candidates.selection.selectedSet}
        selectedSize={candidates.selectedSize}
        untrackedGroups={candidates.untrackedGroups}
        untrackedItems={candidates.untrackedItems}
        onDelete={handleDelete}
        onItemSelection={candidates.selection.updatePath}
        onItemsSelection={(affectedItems, checked) =>
          candidates.selection.updatePaths(
            affectedItems.map((item) => item.path),
            checked,
          )
        }
      />
    </div>
  )
}
