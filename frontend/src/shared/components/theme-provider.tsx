import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

/** Available colour themes. "system" follows the OS preference. */
export type Theme = "dark" | "light" | "system"

interface ThemeProviderState {
  theme: Theme
  /** The concrete theme currently applied to the document ("dark" | "light"). */
  resolvedTheme: "dark" | "light"
  setTheme: (theme: Theme) => void
}

const ThemeProviderContext = createContext<ThemeProviderState | undefined>(
  undefined,
)

function resolveSystemTheme(): "dark" | "light" {
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light"
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

  const [resolvedTheme, setResolvedTheme] = useState<"dark" | "light">(() =>
    theme === "system" ? resolveSystemTheme() : theme,
  )

  useEffect(() => {
    const root = window.document.documentElement
    const applied = theme === "system" ? resolveSystemTheme() : theme

    root.classList.remove("light", "dark")
    root.classList.add(applied)
    setResolvedTheme(applied)

    if (theme !== "system") {
      return
    }

    // Keep the document in sync with OS changes while in "system" mode.
    const media = window.matchMedia("(prefers-color-scheme: dark)")
    const onChange = () => {
      const next = media.matches ? "dark" : "light"
      root.classList.remove("light", "dark")
      root.classList.add(next)
      setResolvedTheme(next)
    }
    media.addEventListener("change", onChange)
    return () => media.removeEventListener("change", onChange)
  }, [theme])

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

export function useTheme(): ThemeProviderState {
  const context = useContext(ThemeProviderContext)
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider")
  }
  return context
}
