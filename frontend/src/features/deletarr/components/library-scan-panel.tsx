import { FolderIcon, RefreshCwIcon } from "lucide-react"

import { StatBlock } from "@/features/deletarr/components/stat-block"
import { Button } from "@/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { formatBytes, formatTimestamp } from "@/shared/lib/format"

interface LibraryScanPanelProps {
  arrDetail: string | null
  arrLabel: string
  arrSourceEnabled: boolean
  currentPath: string
  isBusy: boolean
  isScanning: boolean
  label: string
  lastError: string | null | undefined
  lastScanAt: string | null | undefined
  scanMode: "arr" | "heuristic"
  totalFiles: number
  totalFolders: number
  totalSize: number
  onScan: () => void
}

interface ScanModeBannerProps {
  arrDetail: string | null
  arrLabel: string
  arrSourceEnabled: boolean
  scanMode: "arr" | "heuristic"
}

function ScanModeBanner({
  arrDetail,
  arrLabel,
  arrSourceEnabled,
  scanMode,
}: ScanModeBannerProps) {
  if (scanMode === "arr") {
    return <p>Candidates were checked against {arrLabel} library metadata.</p>
  }
  if (!arrSourceEnabled) {
    return (
      <p className="text-muted-foreground">
        Heuristic scan{arrDetail ? ` — ${arrDetail}` : ""}. Turn on the
        source-of-truth setting to verify candidates against {arrLabel}.
      </p>
    )
  }
  const failureDetail = arrDetail === "Arr source disabled" ? null : arrDetail
  return (
    <p className="text-muted-foreground">
      Heuristic results. Re-scan to verify candidates against {arrLabel} library
      metadata{failureDetail ? ` — ${failureDetail}` : ""}.
    </p>
  )
}

/** Present scan statistics, source status, and scan controls. */
export function LibraryScanPanel({
  arrDetail,
  arrLabel,
  arrSourceEnabled,
  currentPath,
  isBusy,
  isScanning,
  label,
  lastError,
  lastScanAt,
  scanMode,
  totalFiles,
  totalFolders,
  totalSize,
  onScan,
}: LibraryScanPanelProps) {
  return (
    <>
      <section className="grid gap-3 md:grid-cols-4">
        <StatBlock label="Candidate files" value={totalFiles} />
        <StatBlock label="Candidate folders" value={totalFolders} />
        <StatBlock label="Reclaimable" value={formatBytes(totalSize)} />
        <StatBlock
          label="Last scan"
          value={lastScanAt ? formatTimestamp(lastScanAt) : "Not scanned yet"}
        />
      </section>

      <div
        aria-label="Scan mode"
        className="rounded-lg border bg-muted/40 px-4 py-3 text-sm"
      >
        <ScanModeBanner
          arrDetail={arrDetail}
          arrLabel={arrLabel}
          arrSourceEnabled={arrSourceEnabled}
          scanMode={scanMode}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FolderIcon className="size-4 text-muted-foreground" />
            {label} library
          </CardTitle>
          <CardDescription>
            Current path:{" "}
            <span className="font-mono">{currentPath || "Not set"}</span>
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Button type="button" onClick={onScan} disabled={isBusy}>
              <RefreshCwIcon className="size-4" />
              {isScanning ? "Scanning" : "Scan"}
            </Button>
          </div>
          {lastError ? (
            <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {lastError}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </>
  )
}
