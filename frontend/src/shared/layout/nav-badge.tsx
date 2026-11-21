import { Badge } from "@/shared/components/ui/badge"
import { formatCount } from "@/shared/lib/format"
import { cn } from "@/shared/lib/utils"
import { useRemindarrBadgeCount } from "@/shared/lib/queries"
import type { NavBadgeSource } from "@/shared/layout/nav-config"

interface NavBadgeProps {
  /** Which count the badge shows. */
  source: NavBadgeSource
  /**
   * Collapsed rail: a small count over the icon (the caller positions it
   * inside a `relative` icon wrapper). Expanded: a pill after the label.
   */
  collapsed: boolean
}

/**
 * Count badge on a primary navigation entry. Remindarr's shows the total
 * unwatched episodes; it renders nothing while the count is unknown, zero,
 * the module is disabled or the status request fails.
 */
export function NavBadge({ source, collapsed }: NavBadgeProps) {
  // Every source's hook runs unconditionally (rules of hooks); Remindarr is
  // the only source today.
  const counts: Record<NavBadgeSource, number | null> = {
    remindarr: useRemindarrBadgeCount(),
  }
  const count = counts[source]
  if (count === null) return null
  const label = formatCount(count, "unwatched episode")

  return (
    <Badge
      aria-label={label}
      title={label}
      className={cn(
        "tabular-nums",
        collapsed
          ? "absolute -top-2 -right-2.5 h-4 min-w-4 rounded-full px-1 py-0 text-[10px] leading-4 font-semibold"
          : "ml-auto",
      )}
    >
      {count}
    </Badge>
  )
}
