interface StatBlockProps {
  label: string
  value: number | string
}

/** Compact stat card used on the Deletarr and Languagarr scan tabs. */
export function StatBlock({ label, value }: StatBlockProps) {
  return (
    <div className="rounded-lg border bg-background p-4">
      <div className="text-xs font-medium uppercase text-muted-foreground">
        {label}
      </div>
      <div className="mt-2 text-xl font-semibold">{value}</div>
    </div>
  )
}
