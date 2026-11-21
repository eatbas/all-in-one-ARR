import { RefreshCwIcon } from "lucide-react"
import { Link } from "react-router-dom"

import { StatBlock } from "@/shared/components/stat-block"
import { Button } from "@/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { SeriesReminderGroup } from "@/features/remindarr/components/series-reminder-group"
import { StaleBanner } from "@/features/remindarr/components/stale-banner"
import { UnmatchedSeries } from "@/features/remindarr/components/unmatched-series"
import { intervalLabel, tagLabel } from "@/features/remindarr/labels"
import { SETTINGS_TAB_STORAGE_KEY } from "@/features/settings/settings-tab"
import type {
  RemindarrResults,
  RemindarrStatus,
  RemindarrTag,
} from "@/shared/lib/api"
import { formatCount, formatTimestamp } from "@/shared/lib/format"
import {
  useRemindarrResults,
  useRemindarrStatus,
  useRemindarrTags,
  useRunRemindarr,
} from "@/shared/lib/queries"

/** "anime", "anime or kids", "anime, kids or drama". */
function joinTags(names: string[]): string {
  if (names.length <= 1) return names.join("")
  return `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}`
}

/** What the Unwatched episodes card tracks, in the user's own tag names. */
function scopeDescription(
  status: RemindarrStatus,
  tags: RemindarrTag[] | undefined,
): string {
  const { settings } = status
  const names = joinTags(settings.tag_ids.map((id) => tagLabel(id, tags)))
  const scope = settings.monitored_only
    ? `Downloaded, monitored episodes of monitored series tagged ${names}`
    : `Downloaded episodes of series tagged ${names}`
  return `${scope} that the Plex token owner has not watched. Refreshes every ${intervalLabel(settings.interval_minutes)}.`
}

/** Open Settings on the Plex tab (the Settings page restores its last tab). */
function rememberPlexTab() {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(SETTINGS_TAB_STORAGE_KEY, "plex")
  }
}

interface RefreshCardProps {
  status: RemindarrStatus
  tags: RemindarrTag[] | undefined
}

/** The reason "Refresh now" is unavailable, or `null` when it can run. */
function refreshBlocker(status: RemindarrStatus, isRunning: boolean) {
  if (!status.plex_configured) return "plex"
  if (!status.settings.enabled) return "disabled"
  if (isRunning) return "running"
  return null
}

function RefreshCard({ status, tags }: RefreshCardProps) {
  const run = useRunRemindarr()
  const isRunning = status.running || run.isPending
  const blocker = refreshBlocker(status, isRunning)
  const hasTags = status.settings.tag_ids.length > 0

  return (
    <Card>
      <CardHeader>
        <CardTitle>Unwatched episodes</CardTitle>
        {hasTags ? (
          <CardDescription>{scopeDescription(status, tags)}</CardDescription>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            onClick={() => run.mutate()}
            disabled={blocker !== null}
          >
            <RefreshCwIcon
              className={
                blocker === "running" ? "size-4 animate-spin" : "size-4"
              }
            />
            {blocker === "running" ? "Refreshing" : "Refresh now"}
          </Button>
          <RefreshHint blocker={blocker} status={status} />
        </div>
        {blocker === "plex" ? (
          <p className="text-sm text-muted-foreground">
            Plex is not connected.{" "}
            <Link
              to="/settings"
              onClick={rememberPlexTab}
              className="font-medium text-foreground underline underline-offset-4"
            >
              Set up Plex in Settings
            </Link>{" "}
            to see which episodes you have watched.
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

function RefreshHint({
  blocker,
  status,
}: {
  blocker: ReturnType<typeof refreshBlocker>
  status: RemindarrStatus
}) {
  let text: string | null
  if (blocker === "disabled") {
    text = "Enable Remindarr on the Settings tab to refresh."
  } else if (blocker === "running") {
    text = "A refresh is already running."
  } else if (blocker === "plex" || status.last_success_at === null) {
    text = null
  } else {
    text = `${status.counts.tracked_series} series tracked, ${formatCount(status.counts.unwatched, "unwatched episode")}`
  }
  return text ? (
    <span className="text-sm text-muted-foreground">{text}</span>
  ) : null
}

/**
 * The explanatory empty state under the card, or `null` when there are
 * unwatched episodes. "Up to date" is claimed only when the watch state of
 * every tracked episode is known: episodes not in Plex yet and series not
 * found in Plex get a message that does not call them watched.
 */
function emptyState(
  status: RemindarrStatus,
  results: RemindarrResults,
): string | null {
  if (status.settings.tag_ids.length === 0) {
    return "Choose at least one Sonarr tag on the Settings tab to start tracking series."
  }
  if (status.last_success_at === null) {
    return "Refresh now to list the episodes you have not watched yet."
  }
  if (results.series.some((group) => group.episodes.length > 0)) {
    return null
  }
  if (results.series.length === 0 && results.unmatched.length === 0) {
    return "You are up to date: every downloaded episode of your tagged series has been watched in Plex."
  }
  return "Nothing unwatched in Plex. The episodes and series below are not in Plex yet, so their watch state is unknown."
}

function Stats({ status }: { status: RemindarrStatus }) {
  const { counts, last_success_at: lastSuccessAt } = status
  return (
    <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <StatBlock label="Unwatched episodes" value={counts.unwatched} />
      <StatBlock
        label="Series with reminders"
        value={counts.series_with_unwatched}
      />
      <StatBlock label="Not found in Plex" value={counts.unmatched_series} />
      <StatBlock
        label="Last refresh"
        value={lastSuccessAt ? formatTimestamp(lastSuccessAt) : "Never"}
        muted={lastSuccessAt === null}
      />
    </section>
  )
}

/** Remindarr Reminders tab: unwatched episodes grouped by series. */
export function Reminders() {
  const status = useRemindarrStatus()
  const results = useRemindarrResults()
  const { data: tags } = useRemindarrTags()

  // The results wait for the first status (their key holds its refresh
  // generation), so a failed status leaves them pending: report the error
  // before treating a pending query as loading.
  const error = status.error ?? results.error
  if (!error && (status.isPending || results.isPending)) {
    return <p className="text-sm text-muted-foreground">Loading reminders…</p>
  }
  if (error || !status.data || !results.data) {
    return (
      <p className="text-sm text-destructive">
        Could not load Remindarr: {error?.message ?? "no data"}
      </p>
    )
  }

  const current = status.data
  const empty = emptyState(current, results.data)

  return (
    <div className="flex flex-col gap-4">
      <Stats status={current} />
      {current.stale && current.last_error ? (
        <StaleBanner
          error={current.last_error}
          lastAttemptAt={current.last_attempt_at}
          lastSuccessAt={current.last_success_at}
        />
      ) : null}
      <RefreshCard status={current} tags={tags} />
      {empty ? <p className="text-sm text-muted-foreground">{empty}</p> : null}
      {results.data.series.map((group, index) => (
        <SeriesReminderGroup
          key={group.series_id}
          group={group}
          defaultOpen={index === 0 || group.new_today > 0}
        />
      ))}
      <UnmatchedSeries series={results.data.unmatched} />
    </div>
  )
}
