import { Badge } from "@/shared/components/ui/badge"
import { cn } from "@/shared/lib/utils"

/** Visual state of a managed service or Trakt connection pill. */
export type ConnectionState = "connected" | "offline" | "not-set" | "checking"

const DEFAULT_LABELS: Record<ConnectionState, string> = {
  connected: "Connected",
  offline: "Offline",
  "not-set": "Set key",
  checking: "Checking…",
}

const STATE_STYLES: Record<ConnectionState, string> = {
  connected: "border-emerald-500/40 text-emerald-600 dark:text-emerald-400",
  offline: "border-red-500/40 text-red-600 dark:text-red-400",
  "not-set": "border-amber-500/40 text-amber-600 dark:text-amber-400",
  checking: "border-slate-500/40 text-slate-600 dark:text-slate-400",
}

interface ConnectionBadgeProps {
  state: ConnectionState
  /** Optional hover title, e.g. the status snapshot's detail message. */
  detail?: string
  /** Per-state label overrides; defaults are used for any omitted state. */
  labels?: Partial<Record<ConnectionState, string>>
  className?: string
}

/** A small outline badge that maps a connection state to a label and colour. */
export function ConnectionBadge({
  state,
  detail,
  labels,
  className,
}: ConnectionBadgeProps) {
  const label = labels?.[state] ?? DEFAULT_LABELS[state]
  return (
    <Badge
      variant="outline"
      className={cn(STATE_STYLES[state], className)}
      title={detail}
    >
      {label}
    </Badge>
  )
}
