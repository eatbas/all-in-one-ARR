import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

// This is a presence tripwire, not a behavioural test: jsdom applies no
// stylesheets, so the actual `cursor: pointer` on hover cannot be asserted here
// (it is checked manually and via the compiled production bundle). The guard
// exists so a future edit cannot silently drop the base rule that Tailwind v4
// Preflight otherwise leaves as `cursor: default`.
//
// The stylesheet is read straight from disk, anchored to this module's own
// directory (`import.meta.dirname`) rather than the process working directory,
// so the test does not depend on where the runner was invoked. A `?raw` import
// is not usable: the `@tailwindcss/vite` plugin turns it into an empty module in
// the test transform. Resolving via `new URL(..., import.meta.url)` is also not
// reliable: under the jsdom environment that resolution can land on a non-`file`
// scheme and `fileURLToPath` then throws.
const css = readFileSync(resolve(import.meta.dirname, "index.css"), "utf8")

// Strip block comments so a rule that has merely been commented out cannot
// satisfy the assertions below — only active CSS counts.
const activeCss = css.replace(/\/\*[\s\S]*?\*\//g, "")

describe("global cursor base style", () => {
  it("keeps the pointer-cursor base rule in index.css", () => {
    expect(activeCss).toMatch(/button:not\(:disabled\)/)
    expect(activeCss).toMatch(/\[role="button"\]:not\(:disabled\)/)
    expect(activeCss).toContain("cursor: pointer")
  })
})

describe("scrollbar gutter base style", () => {
  // Same presence-tripwire rationale as above: jsdom applies no stylesheets, so
  // the reserved gutter cannot be measured here. The guard ensures a future edit
  // cannot silently drop the rule that stops the layout shifting horizontally as
  // the document scrollbar appears and disappears between routes.
  it("reserves a stable scrollbar gutter in index.css", () => {
    expect(activeCss).toMatch(/html\s*\{[^}]*scrollbar-gutter:\s*stable/)
  })
})

describe("overlay scroll-lock counter-rule", () => {
  // Same presence-tripwire rationale as above: jsdom applies no stylesheets, so
  // the pinned layout cannot be observed here. While a Radix overlay (Select,
  // AlertDialog, DropdownMenu) is open, react-remove-scroll stamps
  // `data-scroll-locked` on <body> and injects `margin-right` scrollbar
  // compensation (a horizontal layout jump we already absorb with the reserved
  // gutter) plus `overflow: hidden` (which turns <body> into a scroll container
  // and detaches the sticky Topbar/Sidebar when the page is scrolled down). The
  // unlayered `html body[data-scroll-locked]` rule cancels both; this guard
  // ensures neither declaration is silently dropped.
  it("keeps both counter-declarations for locked overlays in index.css", () => {
    expect(activeCss).toMatch(
      /html\s+body\[data-scroll-locked\]\s*\{[^}]*margin-right:\s*0\s*!important/,
    )
    expect(activeCss).toMatch(
      /html\s+body\[data-scroll-locked\]\s*\{[^}]*overflow:\s*visible\s*!important/,
    )
  })
})
