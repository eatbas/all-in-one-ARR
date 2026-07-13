import { BrandLogo } from "@/shared/components/brand-logo"
import { ModeToggle } from "@/shared/components/mode-toggle"

/**
 * Top application bar: the app logo, title and the colour-theme toggle. A
 * static child of the fixed-height app shell — nothing scrolls beneath it
 * (only `<main>` scrolls, below), so it needs no sticky positioning and no
 * translucent scrolled-under treatment.
 */
export function Topbar() {
  return (
    <header className="flex h-16 shrink-0 items-center gap-4 border-b bg-background px-4 md:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <BrandLogo className="size-6 shrink-0 text-foreground" />
        <span className="truncate text-lg font-semibold tracking-tight">
          All-in-One ARR
        </span>
      </div>
      <div className="ml-auto flex items-center gap-3">
        <ModeToggle />
      </div>
    </header>
  )
}
