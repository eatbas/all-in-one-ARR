import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Component, type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ThemeProvider } from "@/shared/components/theme-provider"
import { useTheme } from "@/shared/components/theme-context"

const STORAGE_KEY = "test-theme"

/**
 * Error boundary that reports the first render error to `onError`. Used to
 * assert a deliberate throw without React re-dispatching it to jsdom (which
 * would otherwise spew an "uncaught error" trace to stderr).
 */
class CaptureError extends Component<
  { onError: (error: Error) => void; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error) {
    this.props.onError(error)
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}

/** Install a controllable `prefers-color-scheme` media query. */
function installMatchMedia(matches: boolean) {
  const listeners = new Set<(event: MediaQueryListEvent) => void>()
  const mql = {
    matches,
    media: "(prefers-color-scheme: dark)",
    onchange: null,
    addEventListener: (_type: string, cb: (event: MediaQueryListEvent) => void) =>
      listeners.add(cb),
    removeEventListener: (_type: string, cb: (event: MediaQueryListEvent) => void) =>
      listeners.delete(cb),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }
  window.matchMedia = vi
    .fn()
    .mockReturnValue(mql) as unknown as typeof window.matchMedia
  return {
    setMatches(next: boolean) {
      mql.matches = next
      listeners.forEach((cb) => cb({ matches: next } as MediaQueryListEvent))
    },
    listenerCount: () => listeners.size,
  }
}

/** Consumer that surfaces the context for assertions and actions. */
function ThemeProbe() {
  const { theme, resolvedTheme, setTheme } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolvedTheme}</span>
      <button onClick={() => setTheme("light")}>set-light</button>
      <button onClick={() => setTheme("system")}>set-system</button>
    </div>
  )
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.classList.remove("light", "dark")
})

afterEach(() => {
  localStorage.clear()
})

describe("ThemeProvider initialisation", () => {
  it("falls back to the default theme when nothing is stored", () => {
    installMatchMedia(false)
    render(
      <ThemeProvider defaultTheme="dark" storageKey={STORAGE_KEY}>
        <ThemeProbe />
      </ThemeProvider>,
    )

    expect(screen.getByTestId("theme")).toHaveTextContent("dark")
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark")
    expect(document.documentElement).toHaveClass("dark")
  })

  it("prefers a stored theme over the default", () => {
    localStorage.setItem(STORAGE_KEY, "light")
    installMatchMedia(false)
    render(
      <ThemeProvider defaultTheme="dark" storageKey={STORAGE_KEY}>
        <ThemeProbe />
      </ThemeProvider>,
    )

    expect(screen.getByTestId("theme")).toHaveTextContent("light")
    expect(document.documentElement).toHaveClass("light")
  })

  it("resolves the system theme from matchMedia", () => {
    installMatchMedia(true)
    render(
      <ThemeProvider defaultTheme="system" storageKey={STORAGE_KEY}>
        <ThemeProbe />
      </ThemeProvider>,
    )

    expect(screen.getByTestId("theme")).toHaveTextContent("system")
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark")
  })

  it("resolves the system theme to light when the OS prefers light", () => {
    installMatchMedia(false)
    render(
      <ThemeProvider defaultTheme="system" storageKey={STORAGE_KEY}>
        <ThemeProbe />
      </ThemeProvider>,
    )

    expect(screen.getByTestId("resolved")).toHaveTextContent("light")
    expect(document.documentElement).toHaveClass("light")
  })
})

describe("ThemeProvider system tracking", () => {
  it("follows OS changes while in system mode and detaches on unmount", () => {
    const media = installMatchMedia(true)
    const { unmount } = render(
      <ThemeProvider defaultTheme="system" storageKey={STORAGE_KEY}>
        <ThemeProbe />
      </ThemeProvider>,
    )

    expect(screen.getByTestId("resolved")).toHaveTextContent("dark")
    expect(media.listenerCount()).toBe(1)

    act(() => media.setMatches(false))
    expect(screen.getByTestId("resolved")).toHaveTextContent("light")
    expect(document.documentElement).toHaveClass("light")

    act(() => media.setMatches(true))
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark")

    unmount()
    expect(media.listenerCount()).toBe(0)
  })

  it("adds no OS listener for a concrete theme", () => {
    const media = installMatchMedia(false)
    render(
      <ThemeProvider defaultTheme="light" storageKey={STORAGE_KEY}>
        <ThemeProbe />
      </ThemeProvider>,
    )

    expect(media.listenerCount()).toBe(0)
  })
})

describe("setTheme", () => {
  it("persists the choice and re-applies the document class", async () => {
    const user = userEvent.setup()
    installMatchMedia(false)
    render(
      <ThemeProvider defaultTheme="dark" storageKey={STORAGE_KEY}>
        <ThemeProbe />
      </ThemeProvider>,
    )

    await user.click(screen.getByText("set-light"))

    expect(screen.getByTestId("theme")).toHaveTextContent("light")
    expect(screen.getByTestId("resolved")).toHaveTextContent("light")
    expect(localStorage.getItem(STORAGE_KEY)).toBe("light")
    expect(document.documentElement).toHaveClass("light")
  })
})

describe("useTheme guard", () => {
  it("throws when used outside a ThemeProvider", () => {
    // Silence the two channels through which the deliberate throw would reach
    // stderr: React's dev `console.error`, and the `error` event React
    // dispatches on `window` while capturing render errors (which jsdom would
    // otherwise report). The boundary captures the error for the assertion.
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    const suppressWindowError = (event: ErrorEvent) => event.preventDefault()
    window.addEventListener("error", suppressWindowError)
    let captured: Error | undefined
    render(
      <CaptureError onError={(error) => { captured = error }}>
        <ThemeProbe />
      </CaptureError>,
    )
    window.removeEventListener("error", suppressWindowError)
    expect(captured?.message).toBe("useTheme must be used within a ThemeProvider")
    consoleError.mockRestore()
  })
})
