import { useMemo, useState } from "react"
import { ListPlusIcon, RefreshCwIcon } from "lucide-react"

import { DeleteDialog } from "@/features/languagarr/components/delete-dialog"
import { SeriesGroup } from "@/features/languagarr/components/series-group"
import { useSonarrLinkBase } from "@/features/languagarr/sonarr-link"
import {
  groupBySeries,
  isActionable,
} from "@/features/languagarr/review-groups"
import { StatBlock } from "@/shared/components/stat-block"
import { Button } from "@/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import type { LanguagarrItem, LanguagarrScanSummary } from "@/shared/lib/api"
import { formatTimestamp } from "@/shared/lib/format"
import {
  useDeleteLanguagarr,
  useEnqueueLanguagarr,
  useLanguagarrResults,
  useLanguagarrStatus,
  useScanLanguagarr,
} from "@/shared/lib/queries"

interface ResultsProps {
  items: LanguagarrItem[]
  unknown: LanguagarrItem[]
  isBusy: boolean
}

/**
 * Selection and actions for one scan's results. The parent keys this component
 * by the scan timestamp, so a new scan always starts with an empty selection.
 */
function Results({ items, unknown, isBusy }: ResultsProps) {
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set())
  const groups = useMemo(() => groupBySeries(items), [items])
  const enqueue = useEnqueueLanguagarr()
  const deleteFiles = useDeleteLanguagarr()
  const sonarrUrl = useSonarrLinkBase()
  const actionableIds = useMemo(
    () => items.filter(isActionable).map((item) => item.episode_file_id),
    [items],
  )
  const selectedItems = items.filter((item) =>
    selected.has(item.episode_file_id),
  )
  const allSelected =
    actionableIds.length > 0 && selectedItems.length === actionableIds.length
  const disabled = isBusy || enqueue.isPending || deleteFiles.isPending

  function updateSelection(ids: number[], checked: boolean) {
    setSelected((current) => {
      const next = new Set(current)
      for (const id of ids) {
        if (checked) next.add(id)
        else next.delete(id)
      }
      return next
    })
  }

  function clearSelection() {
    setSelected(new Set())
  }

  if (items.length === 0 && unknown.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Every scanned anime file has an English audio track.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={disabled || actionableIds.length === 0}
          onClick={() => updateSelection(actionableIds, !allSelected)}
        >
          {allSelected ? "Clear selection" : "Select all"}
        </Button>
        <Button
          type="button"
          disabled={disabled || selectedItems.length === 0}
          onClick={() =>
            enqueue.mutate(
              selectedItems.map((item) => item.episode_file_id),
              { onSuccess: clearSelection },
            )
          }
        >
          <ListPlusIcon className="size-4" />
          Queue search ({selectedItems.length})
        </Button>
        <DeleteDialog
          items={selectedItems}
          disabled={disabled}
          onConfirm={() =>
            deleteFiles.mutate(
              selectedItems.map((item) => item.episode_file_id),
              { onSuccess: clearSelection },
            )
          }
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Queue search keeps the file and lets the scheduled worker search for a
        better release; Sonarr only swaps it when the release scores higher.
        Files marked “Delete & search” already meet the profile’s score cutoff,
        so Sonarr will never upgrade them on its own.
      </p>
      {sonarrUrl ? null : (
        <p className="text-xs text-muted-foreground">
          Set the Sonarr link URL in Languagarr settings to open each series in
          Sonarr.
        </p>
      )}
      {groups.map((group) => (
        <SeriesGroup
          key={group.seriesId}
          group={group}
          selected={selected}
          onSelect={updateSelection}
          sonarrUrl={sonarrUrl}
        />
      ))}
      {unknown.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Unknown audio ({unknown.length})</CardTitle>
            <CardDescription>
              Sonarr has no audio-language data for these files, so they are
              listed for manual review and never actioned.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-1 font-mono text-xs">
              {unknown.map((item) => (
                <li key={item.episode_file_id} className="truncate">
                  {item.series_title} — {item.relative_path}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}

function ScanStats({ scan }: { scan: LanguagarrScanSummary | undefined }) {
  return (
    <section className="grid gap-3 md:grid-cols-4">
      <StatBlock
        label="Without English audio"
        value={scan?.non_compliant ?? 0}
      />
      <StatBlock label="Unknown audio" value={scan?.unknown ?? 0} />
      <StatBlock label="Files checked" value={scan?.files_scanned ?? 0} />
      <StatBlock
        label="Last scan"
        value={
          scan?.last_scan_at
            ? formatTimestamp(scan.last_scan_at)
            : "Not scanned yet"
        }
      />
    </section>
  )
}

/** Languagarr review tab: scan Sonarr anime files and act on the offenders. */
export function Review() {
  const statusQuery = useLanguagarrStatus()
  const resultsQuery = useLanguagarrResults()
  const scan = useScanLanguagarr()
  const summary = resultsQuery.data?.scan ?? statusQuery.data?.scan
  const isScanning = Boolean(summary?.is_scanning) || scan.isPending
  const busy = isScanning || Boolean(statusQuery.data?.running)
  const profiles = summary?.profiles_in_scope.length
    ? summary.profiles_in_scope
    : (statusQuery.data?.settings.quality_profile_names ?? [])

  return (
    <div className="flex flex-col gap-4">
      <ScanStats scan={summary} />
      <Card>
        <CardHeader>
          <CardTitle>Anime audio audit</CardTitle>
          <CardDescription>
            Checks the real audio tracks of every episode file on the{" "}
            {profiles.join(", ") || "configured"} quality profile(s). A file
            passes when it has an English audio track; English-only and
            dual-audio files are both fine.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <Button type="button" onClick={() => scan.mutate()} disabled={busy}>
              <RefreshCwIcon className="size-4" />
              {isScanning ? "Scanning" : "Scan"}
            </Button>
            {summary?.last_scan_at ? (
              <span className="text-sm text-muted-foreground">
                {summary.series_scanned} series, {summary.files_scanned} files
                checked
              </span>
            ) : null}
          </div>
          {summary?.last_error ? (
            <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {summary.last_error}
            </p>
          ) : null}
        </CardContent>
      </Card>
      {resultsQuery.isLoading || !resultsQuery.data ? (
        <p className="text-sm text-muted-foreground">Loading results…</p>
      ) : !resultsQuery.data.scan.last_scan_at ? (
        <p className="text-sm text-muted-foreground">
          Run a scan to list anime files without an English audio track.
        </p>
      ) : (
        <Results
          key={resultsQuery.data.scan.last_scan_at}
          items={resultsQuery.data.results}
          unknown={resultsQuery.data.unknown}
          isBusy={busy}
        />
      )}
    </div>
  )
}
