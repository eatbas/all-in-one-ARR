import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react"

import {
  ThemeProviderContext,
  type Theme,
  type ThemeProviderState,
} from "@/shared/components/theme-context"

const SYSTEM_THEME_QUERY = "(prefers-color-scheme: dark)"

/** Read the current OS colour-scheme preference as a concrete theme. */
function getSystemTheme(): "dark" | "light" {
  return window.matchMedia(SYSTEM_THEME_QUERY).matches ? "dark" : "light"
}

interface ThemeProviderProps {
  children: ReactNode
  /** Initial theme used when nothing is stored. Defaults to dark. */
  defaultTheme?: Theme
  /** localStorage key under which the chosen theme is persisted. */
  storageKey?: string
}

export function ThemeProvider({
  children,
  defaultTheme = "dark",
  storageKey = "aio-arr-theme",
}: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(() => {
    const stored = localStorage.getItem(storageKey) as Theme | null
    return stored ?? defaultTheme
  })

  // Subscribe to OS changes only while actually following the system theme, so a
  // concrete choice attaches no listener. `useSyncExternalStore` reads the live
  // preference on every render, so the resolved theme can never go stale and no
  // state is updated inside an effect.
  const subscribeToSystemTheme = useCallback(
    (onStoreChange: () => void) => {
      if (theme !== "system") {
        return () => {}
      }
      const media = window.matchMedia(SYSTEM_THEME_QUERY)
      media.addEventListener("change", onStoreChange)
      return () => media.removeEventListener("change", onStoreChange)
    },
    [theme],
  )
  const systemTheme = useSyncExternalStore(
    subscribeToSystemTheme,
    getSystemTheme,
  )

  const resolvedTheme: "dark" | "light" =
    theme === "system" ? systemTheme : theme

  // Apply the resolved theme to the document. This synchronises an external
  // system (the DOM) and intentionally performs no React state updates.
  useEffect(() => {
    const root = window.document.documentElement
    root.classList.remove("light", "dark")
    root.classList.add(resolvedTheme)
  }, [resolvedTheme])

  const value = useMemo<ThemeProviderState>(
    () => ({
      theme,
      resolvedTheme,
      setTheme: (next: Theme) => {
        localStorage.setItem(storageKey, next)
        setThemeState(next)
      },
    }),
    [theme, resolvedTheme, storageKey],
  )

  return (
    <ThemeProviderContext.Provider value={value}>
      {children}
    </ThemeProviderContext.Provider>
  )
}
