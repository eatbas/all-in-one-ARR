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
