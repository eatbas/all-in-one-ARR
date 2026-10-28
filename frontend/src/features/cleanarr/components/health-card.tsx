import { InfoIcon, TriangleAlertIcon } from "lucide-react"

import { Badge } from "@/shared/components/ui/badge"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { PILL_BASE, PILL_STYLES, sourceLabel } from "@/features/cleanarr/labels"
import type { CleanarrHealthWarning } from "@/shared/lib/api"
import { cn } from "@/shared/lib/utils"

interface HealthCardProps {
  health: CleanarrHealthWarning[]
  /** Whether Cleanarr has run at least once (health is stored per run). */
  hasRun: boolean
}

/** Read-only SABnzbd and Arr health checks from the last run. */
export function HealthCard({ health, hasRun }: HealthCardProps) {
  const warnings = health.filter((entry) => entry.level === "warning").length

  return (
    <Card>
      <CardHeader>
        <CardTitle>Health checks</CardTitle>
        <CardDescription>
          Read-only checks of SABnzbd and Arr download settings. Cleanarr never
          changes them.
        </CardDescription>
        {warnings > 0 ? (
          <CardAction>
            <span className={cn(PILL_BASE, PILL_STYLES.amber)}>
              <TriangleAlertIcon className="size-3" aria-hidden="true" />
              {warnings} {warnings === 1 ? "warning" : "warnings"}
            </span>
          </CardAction>
        ) : null}
      </CardHeader>
      <CardContent>
        {health.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {hasRun
              ? "No warnings from the last run."
              : "Health checks run with each Cleanarr run."}
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {health.map((entry) => (
              <li
                key={`${entry.source}-${entry.code}`}
                className="flex items-start gap-2 text-sm"
              >
                {entry.level === "warning" ? (
                  <TriangleAlertIcon
                    className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400"
                    aria-label="Warning"
                  />
                ) : (
                  <InfoIcon
                    className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                    aria-label="Unknown"
                  />
                )}
                <div>
                  <Badge variant="outline" className="mr-2">
                    {sourceLabel(entry.source)}
                  </Badge>
                  <span
                    className={cn(
                      entry.level === "info" && "text-muted-foreground",
                    )}
                  >
                    {entry.detail}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
