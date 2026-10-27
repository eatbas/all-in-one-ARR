import { cn } from "@/shared/lib/utils"

interface StatBlockProps {
  label: string
  value: number | string
  /** Dim the value, e.g. an unavailable figure shown as "—". */
  muted?: boolean
}

/** Compact stat card used on the Dashboard and the Deletarr/Languagarr scan tabs. */
export function StatBlock({ label, value, muted = false }: StatBlockProps) {
  return (
    <div className="rounded-lg border bg-background p-4">
      <div className="text-xs font-medium uppercase text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "mt-2 text-xl font-semibold tabular-nums",
          muted && "text-muted-foreground",
        )}
      >
        {value}
      </div>
    </div>
  )
}
