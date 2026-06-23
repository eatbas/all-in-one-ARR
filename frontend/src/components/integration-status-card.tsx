import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { ServiceStatus } from "@/lib/api"

interface IntegrationStatusCardProps {
  name: string
  label: string
  status: ServiceStatus | undefined
  compact?: boolean
}

/** Small card showing the current health of a single integration. */
export function IntegrationStatusCard({
  name,
  label,
  status,
  compact = false,
}: IntegrationStatusCardProps) {
  const ok = status?.ok ?? false
  const detail = status?.detail ?? "Not checked yet"

  return (
    <Card className={cn("flex flex-col", compact && "gap-1 py-0")}>
      <CardHeader
        className={cn(
          "flex flex-row items-center justify-between gap-2 space-y-0",
          compact ? "px-3 py-2 pb-1" : "pb-2",
        )}
      >
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
        <span
          className={cn(
            "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium",
            ok
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
              : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
          )}
        >
          {ok ? "Online" : "Offline"}
        </span>
      </CardHeader>
      <CardContent className={cn("flex-1", compact && "px-3 py-1 pt-0")}>
        <CardDescription className="text-xs line-clamp-1">
          {detail}
        </CardDescription>
        {!compact ? (
          <p className="mt-2 text-[10px] uppercase tracking-wider text-muted-foreground">
            {name}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
