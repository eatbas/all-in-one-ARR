import { ActivityIcon, LineChartIcon, PauseIcon, PlayIcon } from "lucide-react"

import { Button } from "@/shared/components/ui/button"
import { cn } from "@/shared/lib/utils"
import { APP_BRAND } from "@/features/findarr/components/app-brand"
import type { FindarrAppName, FindarrAppStatus, FindarrStatus } from "@/shared/lib/api"

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
 * Current-window progress as two non-ratio facts: how many have been searched
 * (cumulative this window) and how many of the last run's wanted set are still
 * left. Avoiding a "searched/wanted" ratio means it can never read backwards
 * when the wanted list shrinks faster than items are searched.
 */
function windowLabel(searched: number, wanted: number): string {
  const remaining = Math.max(0, wanted - searched)
  return wanted > 0
    ? `${searched} searched · ${remaining} left this window`
    : `${searched} searched this window`
}

/**
 * One redesigned Sonarr/Radarr tile for the Findarr Status tab: a glowing
 * official logo on a dark badge, an Active/Paused pill (synced to the app's
 * Findarr enable state), an API-usage pill, the all-time searches/upgrades
 * counters (with a "this window" sub-line), a plain-language last-run activity
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
  const { processed, lifetime, wanted, activity } = status

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
          <p className={cn("text-4xl font-bold tabular-nums", brand.accentClass)}>
            {lifetime.missing}
          </p>
          <p className="mt-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Searches Triggered
          </p>
          <p
            className="mt-0.5 text-[11px] text-muted-foreground tabular-nums"
            aria-label={`Searches ${windowLabel(processed.missing, wanted.missing)}`}
          >
            {windowLabel(processed.missing, wanted.missing)}
          </p>
        </div>
        <div>
          <p className={cn("text-4xl font-bold tabular-nums", brand.accentClass)}>
            {lifetime.upgrade}
          </p>
          <p className="mt-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Upgrades Triggered
          </p>
          <p
            className="mt-0.5 text-[11px] text-muted-foreground tabular-nums"
            aria-label={`Upgrades ${windowLabel(processed.upgrade, wanted.upgrade)}`}
          >
            {windowLabel(processed.upgrade, wanted.upgrade)}
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
