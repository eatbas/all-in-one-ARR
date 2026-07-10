/**
 * Global test setup: jest-dom matchers plus the jsdom polyfills that the
 * `ThemeProvider` and the Radix UI primitives depend on. Runs before every test
 * file (see `test.setupFiles` in `vite.config.ts`).
 */
import "@testing-library/jest-dom/vitest"
import { vi } from "vitest"

// jsdom does not implement `matchMedia`; `ThemeProvider` and some Radix
// primitives call it. Default to the "light" preference (`matches: false`);
// tests that need OS-dark or `change` events override `window.matchMedia`
// locally.
window.matchMedia = vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  addListener: vi.fn(),
  removeListener: vi.fn(),
  dispatchEvent: vi.fn(),
}))

// jsdom lacks `ResizeObserver`, which Radix observes for positioning.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver =
  ResizeObserverStub as unknown as typeof ResizeObserver

// jsdom lacks `IntersectionObserver`; the Trending grid uses one to drive its
// infinite scroll. Default to an inert stub so components can construct one;
// tests that need to simulate "scrolled into view" override
// `window.IntersectionObserver` locally (see Trending.test.tsx).
class IntersectionObserverStub {
  readonly root = null
  readonly rootMargin = ""
  readonly thresholds: ReadonlyArray<number> = []
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return []
  }
}
globalThis.IntersectionObserver =
  IntersectionObserverStub as unknown as typeof IntersectionObserver

// Node 22+ ships built-in `localStorage`/`sessionStorage` globals that are
// unavailable without `--localstorage-file`; they shadow jsdom's Web Storage in
// the test env, so a bare `localStorage.clear()` throws on `undefined`. Install
// deterministic in-memory Storage for both so the suite behaves the same on
// every Node version; tests still `clear()` per `beforeEach` and may stub them
// locally (restored by `vi.unstubAllGlobals()`).
class MemoryStorage {
  private store = new Map<string, string>()
  get length(): number {
    return this.store.size
  }
  clear(): void {
    this.store.clear()
  }
  getItem(key: string): string | null {
    return this.store.get(key) ?? null
  }
  key(index: number): string | null {
    return [...this.store.keys()][index] ?? null
  }
  removeItem(key: string): void {
    this.store.delete(key)
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value))
  }
}
globalThis.localStorage = new MemoryStorage() as unknown as Storage
globalThis.sessionStorage = new MemoryStorage() as unknown as Storage

// jsdom either omits or throws for these element APIs that Radix touches when a
// menu/dropdown opens; replace them with no-ops so interactions can proceed.
Element.prototype.scrollIntoView = (): void => {}
Element.prototype.hasPointerCapture = (): boolean => false
Element.prototype.setPointerCapture = (): void => {}
Element.prototype.releasePointerCapture = (): void => {}
