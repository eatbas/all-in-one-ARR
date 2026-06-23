/**
 * Global test setup: jest-dom matchers plus the jsdom polyfills that the
 * `ThemeProvider` and the Radix UI primitives depend on. Runs before every test
 * file (see `test.setupFiles` in `vite.config.ts`).
 */
import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

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

// jsdom either omits or throws for these element APIs that Radix touches when a
// menu/dropdown opens; replace them with no-ops so interactions can proceed.
Element.prototype.scrollIntoView = (): void => {}
Element.prototype.hasPointerCapture = (): boolean => false
Element.prototype.setPointerCapture = (): void => {}
Element.prototype.releasePointerCapture = (): void => {}
