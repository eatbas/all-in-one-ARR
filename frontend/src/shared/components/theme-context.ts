import { createContext, useContext } from "react"

/** Available colour themes. "system" follows the OS preference. */
export type Theme = "dark" | "light" | "system"

export interface ThemeProviderState {
  theme: Theme
  /** The concrete theme currently applied to the document ("dark" | "light"). */
  resolvedTheme: "dark" | "light"
  setTheme: (theme: Theme) => void
}

/**
 * Theme context and its consumer hook live in this module — separate from the
 * `ThemeProvider` component — so the provider file only exports components and
 * React Fast Refresh boundaries stay intact (react-refresh/only-export-components).
 */
export const ThemeProviderContext = createContext<
  ThemeProviderState | undefined
>(undefined)

export function useTheme(): ThemeProviderState {
  const context = useContext(ThemeProviderContext)
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider")
  }
  return context
}
