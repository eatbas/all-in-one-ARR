import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import type { DashboardDisk } from "@/shared/lib/api"
import { formatBytes } from "@/shared/lib/format"

const APP_LABELS: Record<DashboardDisk["app"], string> = {
  sonarr: "Sonarr",
  radarr: "Radarr",
}

/** Percentage of a disk in use, rounded; 0 when its size is unknown. */
function usedPercent(disk: DashboardDisk): number {
  if (disk.total_bytes <= 0) {
    return 0
  }
  const used = disk.total_bytes - disk.free_bytes
  return Math.round((used / disk.total_bytes) * 100)
}

interface DiskSpaceCardProps {
  disks: DashboardDisk[]
}

/** Free and used space on every Sonarr and Radarr mount. */
export function DiskSpaceCard({ disks }: DiskSpaceCardProps) {
  return (
    <Card aria-labelledby="disk-space-title">
      <CardHeader>
        <CardTitle id="disk-space-title">Disk space</CardTitle>
        <CardDescription>
          Free space on each Sonarr and Radarr root folder.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {disks.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No disk space reported yet.
          </p>
        ) : (
          <ul className="flex flex-col gap-4">
            {disks.map((disk) => (
              <DiskRow key={`${disk.app}:${disk.path}`} disk={disk} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function DiskRow({ disk }: { disk: DashboardDisk }) {
  const app = APP_LABELS[disk.app]
  const name = disk.label ?? disk.path
  const used = usedPercent(disk)

  return (
    <li>
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-sm">
        <span>
          <span className="font-medium">{app}</span>
          {disk.label ? ` · ${disk.label}` : null}{" "}
          <code className="font-mono text-xs text-muted-foreground">
            {disk.path}
          </code>
        </span>
        <span className="text-muted-foreground tabular-nums">
          {formatBytes(disk.free_bytes)} free of {formatBytes(disk.total_bytes)}
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={`${app} ${name} used`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={used}
        className="mt-1.5 h-2 overflow-hidden rounded-full bg-muted"
      >
        <div
          className="h-full rounded-full bg-chart-2"
          style={{ width: `${used}%` }}
        />
      </div>
    </li>
  )
}
