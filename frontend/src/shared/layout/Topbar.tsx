import { ModeToggle } from "@/shared/components/mode-toggle"

/** Top application bar: the app logo, title and the colour-theme toggle. */
export function Topbar() {
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60 md:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <img src="/logo.svg" alt="" className="size-6 shrink-0" />
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
