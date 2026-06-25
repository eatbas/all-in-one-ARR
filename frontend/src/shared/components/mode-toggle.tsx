import { MoonIcon, SunIcon } from "lucide-react"

import { Button } from "@/shared/components/ui/button"
import { useTheme } from "@/shared/components/theme-context"

/** Button that toggles the colour theme between light and dark. */
export function ModeToggle() {
  const { resolvedTheme, setTheme } = useTheme()

  function toggleTheme() {
    setTheme(resolvedTheme === "dark" ? "light" : "dark")
  }

  return (
    <Button
      variant="outline"
      size="icon"
      aria-label="Toggle theme"
      onClick={toggleTheme}
    >
      <SunIcon className="size-[1.2rem] scale-100 rotate-0 transition-all dark:scale-0 dark:-rotate-90" />
      <MoonIcon className="absolute size-[1.2rem] scale-0 rotate-90 transition-all dark:scale-100 dark:rotate-0" />
      <span className="sr-only">Toggle theme</span>
    </Button>
  )
}
