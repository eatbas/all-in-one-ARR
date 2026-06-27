import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { Badge } from "@/shared/components/ui/badge"
import { cn } from "@/shared/lib/utils"

interface ClientCardProps {
  label: string
  online: boolean
  speed: number
  active: number
  queue: number
  paused?: boolean
}

/**
 * Presentational card showing one download client's live statistics. Reused for
 * both qBittorrent and SABnzbd so the two client blocks stay consistent.
 */
export function ClientCard({
  label,
  online,
  speed,
  active,
  queue,
  paused,
}: ClientCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{label}</CardTitle>
        <div className="flex items-center gap-2">
          {paused !== undefined && (
            <Badge variant={paused ? "destructive" : "secondary"}>
              {paused ? "PAUSED" : "RESUMED"}
            </Badge>
          )}
          <Badge
            variant={online ? "default" : "outline"}
            className={
              online
                ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
            }
          >
            {online ? "Online" : "Offline"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <dl
          className={cn(
            "grid grid-cols-3 gap-4 text-sm",
            !online && "opacity-60",
          )}
        >
          <div>
            <dt className="text-muted-foreground">Speed</dt>
            <dd className="font-medium">{speed.toFixed(2)} MB/s</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Active</dt>
            <dd className="font-medium">{active}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Queue</dt>
            <dd className="font-medium">{queue}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  )
}
