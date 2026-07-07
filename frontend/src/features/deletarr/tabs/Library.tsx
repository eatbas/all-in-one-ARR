import { useMemo, useState } from "react"
import { FolderIcon, RefreshCwIcon, Trash2Icon } from "lucide-react"

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
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import {
  ResultGroupPanel,
  type ResultGroup,
} from "@/features/deletarr/components/result-group-panel"
import { StatBlock } from "@/features/deletarr/components/stat-block"
import type { DeletarrLibraryType, DeletarrScanItem } from "@/shared/lib/api"
import { formatBytes, formatTimestamp } from "@/shared/lib/format"
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

function groupResults(items: DeletarrScanItem[]): ResultGroup[] {
  const grouped = new Map<string, ResultGroup>()

  for (const item of items) {
    const key = item.movie_folder_path ?? item.parent
    const title = item.movie_folder ?? item.parent
    const subtitle = item.movie_folder_path ?? item.parent
    const existing = grouped.get(key)

    if (existing) {
      existing.items.push(item)
      if (existing.videos.length === 0 && item.videos_in_folder.length > 0) {
        existing.videos = item.videos_in_folder
      }
    } else {
      grouped.set(key, {
        key,
        title,
        subtitle,
        items: [item],
        videos: item.videos_in_folder,
      })
    }
  }

  return [...grouped.values()]
}

/** Whole folders / loose files the library manager does not track at all. */
function isOrphanItem(item: DeletarrScanItem): boolean {
  return (
    item.reason.startsWith("Orphaned folder") ||
    item.reason.startsWith("Loose file")
  )
}

function lastScanLabel(value: string | null | undefined): string {
  return value ? formatTimestamp(value) : "Not scanned yet"
}

interface LibraryProps {
  type: DeletarrLibraryType
}

/** Deletarr scan/delete tab: review and remove junk for one library. */
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
  const managedGroups = useMemo(
    () => groupResults(items.filter((item) => !isOrphanItem(item))),
    [items],
  )
  const orphanGroups = useMemo(
    () => groupResults(items.filter(isOrphanItem)),
    [items],
  )
  const defaultSelectionKey = useMemo(
    () =>
      items.map((item) => `${item.path}:${String(item.is_checked)}`).join("|"),
    [items],
  )
  const defaultSelectedPaths = useMemo(
    () => items.filter((item) => item.is_checked).map((item) => item.path),
    [items],
  )
  const [selectionEdit, setSelectionEdit] = useState<{
    key: string
    paths: string[]
  }>({ key: "", paths: [] })

  const selectedPaths =
    selectionEdit.key === defaultSelectionKey
      ? selectionEdit.paths
      : defaultSelectedPaths
  const selectedSet = useMemo(() => new Set(selectedPaths), [selectedPaths])
  const selectedItems = useMemo(
    () => items.filter((item) => selectedSet.has(item.path)),
    [items, selectedSet],
  )
  const selectedSize = selectedItems.reduce(
    (total, item) => total + item.size,
    0,
  )
  const isBusy =
    Boolean(status?.stats.is_scanning || results?.stats.is_scanning) ||
    scanLibrary.isPending ||
    deleteItems.isPending
  const stats = results?.stats ?? status?.stats
  const scanMode = results?.scan_mode ?? status?.scan_mode ?? "heuristic"
  const arrDetail = status?.arr_detail ?? results?.arr_detail ?? null

  function updateSelection(path: string, checked: boolean) {
    setSelectionEdit((current) => {
      const currentPaths =
        current.key === defaultSelectionKey
          ? current.paths
          : defaultSelectedPaths
      if (checked) {
        return {
          key: defaultSelectionKey,
          paths: [...currentPaths, path],
        }
      }
      return {
        key: defaultSelectionKey,
        paths: currentPaths.filter((itemPath) => itemPath !== path),
      }
    })
  }

  function updateGroupSelection(group: ResultGroup, checked: boolean) {
    const paths = group.items.map((item) => item.path)
    setSelectionEdit((current) => {
      const currentPaths =
        current.key === defaultSelectionKey
          ? current.paths
          : defaultSelectedPaths
      if (!checked) {
        return {
          key: defaultSelectionKey,
          paths: currentPaths.filter((path) => !paths.includes(path)),
        }
      }
      return {
        key: defaultSelectionKey,
        paths: [
          ...currentPaths,
          ...paths.filter((path) => !currentPaths.includes(path)),
        ],
      }
    })
  }

  function handleDelete() {
    deleteItems.mutate(
      { type, paths: selectedPaths },
      {
        onSuccess: () =>
          setSelectionEdit({ key: defaultSelectionKey, paths: [] }),
      },
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <section className="grid gap-3 md:grid-cols-4">
        <StatBlock label="Junk files" value={stats?.total_files ?? 0} />
        <StatBlock label="Junk folders" value={stats?.total_folders ?? 0} />
        <StatBlock
          label="Reclaimable"
          value={formatBytes(stats?.total_size ?? 0)}
        />
        <StatBlock
          label="Last scan"
          value={lastScanLabel(status?.last_scan_at)}
        />
      </section>

      <div
        aria-label="Scan mode"
        className="rounded-lg border bg-muted/40 px-4 py-3 text-sm"
      >
        {scanMode === "arr" ? (
          <p>
            Verified against{" "}
            <span className="font-medium">{ARR_LABELS[type]}</span>: only files{" "}
            {ARR_LABELS[type]} does not track are shown.
          </p>
        ) : (
          <p className="text-muted-foreground">
            Heuristic scan{arrDetail ? ` — ${arrDetail}` : ""}. Connect{" "}
            {ARR_LABELS[type]} to verify candidates against your library.
          </p>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FolderIcon className="size-4 text-muted-foreground" />
            {LIBRARY_LABELS[type]} library
          </CardTitle>
          <CardDescription>
            Current path:{" "}
            <span className="font-mono">{currentPath || "Not set"}</span>
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Button
              type="button"
              onClick={() => scanLibrary.mutate(type)}
              disabled={isBusy}
            >
              <RefreshCwIcon className="size-4" />
              {status?.stats.is_scanning ? "Scanning" : "Scan"}
            </Button>
          </div>

          {status?.last_error ? (
            <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {status.last_error}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <div className="flex flex-col gap-3 rounded-lg border bg-background p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-base font-semibold">Scan results</h2>
          <p className="text-sm text-muted-foreground">
            {selectedPaths.length} of {items.length} candidate(s) selected.
          </p>
        </div>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              type="button"
              variant="destructive"
              disabled={selectedPaths.length === 0 || deleteItems.isPending}
            >
              <Trash2Icon className="size-4" />
              Delete selected
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>
                Delete selected Deletarr items?
              </AlertDialogTitle>
              <AlertDialogDescription>
                This will delete {selectedPaths.length} current scan result(s)
                from the {LIBRARY_LABELS[type].toLowerCase()} library and
                reclaim about {formatBytes(selectedSize)}.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={handleDelete}>
                Delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      {resultsQuery.isLoading ? (
        <p className="rounded-lg border bg-background p-4 text-sm text-muted-foreground">
          Loading Deletarr results...
        </p>
      ) : managedGroups.length === 0 && orphanGroups.length === 0 ? (
        <p className="rounded-lg border bg-background p-4 text-sm text-muted-foreground">
          No junk candidates found for {LIBRARY_LABELS[type].toLowerCase()}.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {managedGroups.map((group) => (
            <ResultGroupPanel
              key={group.key}
              group={group}
              selectedSet={selectedSet}
              onGroupSelection={updateGroupSelection}
              onItemSelection={updateSelection}
            />
          ))}
          {orphanGroups.length > 0 ? (
            <div className="flex flex-col gap-3">
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3">
                <h3 className="text-sm font-semibold">
                  Not in your {LIBRARY_LABELS[type].toLowerCase()} library
                </h3>
                <p className="text-xs text-muted-foreground">
                  Whole folders and loose files {ARR_LABELS[type]} does not
                  track. These are unchecked by default — review carefully
                  before deleting.
                </p>
              </div>
              {orphanGroups.map((group) => (
                <ResultGroupPanel
                  key={group.key}
                  group={group}
                  selectedSet={selectedSet}
                  onGroupSelection={updateGroupSelection}
                  onItemSelection={updateSelection}
                />
              ))}
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
