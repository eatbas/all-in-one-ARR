import type { Theme } from "@/shared/components/theme-provider"

/** The colour-theme choices offered in the UI (header toggle + General tab). */
export const THEME_OPTIONS: ReadonlyArray<{ value: Theme; label: string }> = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
]
