import { ActivityIcon, LineChartIcon, PauseIcon, PlayIcon } from "lucide-react"

import { Button } from "@/shared/components/ui/button"
import { cn } from "@/shared/lib/utils"
import { APP_BRAND } from "@/features/findarr/components/app-brand"
import type {
  FindarrAppName,
  FindarrAppStatus,
  FindarrStatus,
} from "@/shared/lib/api"

interface FindarrAppCardProps {
  app: FindarrAppName
  status: FindarrAppStatus
  hourly: FindarrStatus["hourly"]
  /** Whether this app is effectively active (Findarr + this app enabled) vs Paused. */
  enabled: boolean
  onRun: () => void
  isRunning: boolean
}

/**
 * Backlog as two non-ratio facts: how many items the last run found wanted, and
 * how many are waiting out their retry delay (each search that finds nothing
 * doubles an item's wait). No ratio, so it never reads backwards when the
 * wanted list shrinks between runs.
 */
function backlogLabel(wanted: number, waiting: number): string {
  return waiting > 0
    ? `${wanted} wanted · ${waiting} waiting to retry`
    : `${wanted} wanted`
}

/**
 * One redesigned Sonarr/Radarr tile for the Findarr Status tab: a glowing
 * official logo on a dark badge, an Active/Paused pill (synced to the app's
 * Findarr enable state), an API-usage pill, the all-time searches/upgrades
 * counters (with a wanted/waiting sub-line), a plain-language last-run activity
 * line, and a per-app Run button. The headline numbers are the reset-proof
 * lifetime tallies so a caught-up app never collapses to a bare 0. The card
 * surface follows the app theme; the brand accents carry light/dark variants so
 * they stay legible on both backgrounds.
 */
export function FindarrAppCard({
  app,
  status,
  hourly,
  enabled,
  onRun,
  isRunning,
}: FindarrAppCardProps) {
  const brand = APP_BRAND[app]
  const { cooldown, lifetime, wanted, activity } = status

  return (
    <section
      aria-label={brand.label}
      className="relative flex flex-col items-center gap-5 rounded-xl border bg-card p-6 text-card-foreground"
    >
      <div className="flex flex-wrap items-center justify-center gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
            enabled
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
              : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
          )}
        >
          {enabled ? (
            <ActivityIcon className="size-3" />
          ) : (
            <PauseIcon className="size-3" />
          )}
          {enabled ? "Active" : "Paused"}
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
          <LineChartIcon className="size-3" />
          {`API ${hourly.used} / ${hourly.limit}`}
        </span>
      </div>

      <div
        className={cn(
          "flex size-28 items-center justify-center rounded-full border-2",
          brand.discClass,
          brand.ringClass,
        )}
      >
        <img src={brand.logoSrc} alt="" className="size-16" />
      </div>

      <p className="text-lg font-semibold tracking-wide">{brand.label}</p>

      <div className="grid w-full grid-cols-2 gap-4 text-center">
        <div>
          <p
            className={cn("text-4xl font-bold tabular-nums", brand.accentClass)}
          >
            {lifetime.missing}
          </p>
          <p className="mt-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Searches Triggered
          </p>
          <p
            className="mt-0.5 text-[11px] text-muted-foreground tabular-nums"
            aria-label={`Searches ${backlogLabel(wanted.missing, cooldown.missing)}`}
          >
            {backlogLabel(wanted.missing, cooldown.missing)}
          </p>
        </div>
        <div>
          <p
            className={cn("text-4xl font-bold tabular-nums", brand.accentClass)}
          >
            {lifetime.upgrade}
          </p>
          <p className="mt-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Upgrades Triggered
          </p>
          <p
            className="mt-0.5 text-[11px] text-muted-foreground tabular-nums"
            aria-label={`Upgrades ${backlogLabel(wanted.upgrade, cooldown.upgrade)}`}
          >
            {backlogLabel(wanted.upgrade, cooldown.upgrade)}
          </p>
        </div>
      </div>

      <p className="text-center text-xs text-muted-foreground">{activity}</p>

      <Button size="sm" onClick={onRun} disabled={isRunning}>
        <PlayIcon className="size-4" />
        Run {brand.label}
      </Button>
    </section>
  )
}
