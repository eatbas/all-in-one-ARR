# Implementation Plan

Uniform, hover-expanding poster pills for the Trending grid.

## Objective

Rework the four corner controls on each Trending poster (`TrendingCard`) so they:

1. **Share one size.** The source-link pill, the green "available" tick, the amber
   "in-progress" dotted circle and the Add "+" pill are currently 24px, 20px, 20px
   and 32px respectively. Standardise **all** of them on a **32px (`h-8`)** height,
   the current Add button's height (user-selected target).
2. **Drop the top-left "Tracked" badge** entirely.
3. **Expand consistently on hover/focus.** All three functional pills (source link,
   status indicator, Add) reveal a short text label on their own hover/keyboard
   focus — the reveal the Add pill already has (`+` → `Add +`).
4. **Never overlap at 7-per-row.** At the `lg:grid-cols-7` density the cards are
   narrowest; the two bottom-corner pills must not collide when a label expands.

Scope is the Trending feature only:
`frontend/src/features/trending/components/*` plus their co-located tests. No API,
routing or backend change.

## Current state

Resolved from the repository (no branch target supplied; this is uncommitted work
on `main`, already staged as modified/untracked per `git status`).

- **`components/TrendingCard.tsx`** — owns the poster and its four absolutely
  positioned overlays:
  - `absolute left-1 top-1` — **`Tracked` `Badge`** (`variant="outline"`), gated on
    `item.already_tracked`. *(to remove)*
  - `absolute right-1 top-1` — source-link `<a>`: `p-1` + `ExternalLinkIcon size-4`
    ≈ **24px**, `rounded-md`. Label lives only in `title`/`aria-label`.
  - `absolute left-1 bottom-1` — `<TrendingStatusIndicator>`. **20px** circle.
  - `absolute right-1 bottom-1` — `<AddToListControl>`. Button `size="sm"` = **`h-8`**
    (32px), expands `+` → `Add +` on `group/add` hover/focus.
  - The hover title overlay uses `pb-9` (36px) to clear the bottom pills; `h-8`
    pills + `bottom-1` = 36px, so `pb-9` still clears them exactly — keep it.
- **`components/TrendingStatusIndicator.tsx`** — renders either a `size-5`
  `bg-emerald-500` circle with `CheckIcon size-3.5` (available) or a `size-5`
  `border-2 border-dotted border-amber-500` circle (pending). The precise status is
  carried only by `title`/`aria-label`; there is no visible expanding label.
  `pendingLabel()` returns the Seer label (`Requested`/`Processing`/`Partial`) or the
  long `"In library, media not downloaded"`.
- **`components/AddToListControl.tsx`** — `ADD_BUTTON` constant + `AddButtonBody()`
  helper implement the canonical reveal: a collapsing `<span>`
  (`max-w-0 opacity-0` → `group-hover/add:max-w-10 group-hover/add:opacity-100`,
  plus the `group-focus-visible/add` pair and `motion-reduce:transition-none`).
  This is the reference pattern to generalise.
- **`Trending.tsx`** — `GRID_COLS[7] = "... lg:grid-cols-7"` is the narrowest card
  width. Note the in-file comment: **Tailwind JIT compiles only literal class names**
  (why `GRID_COLS` is a literal record) — the shared pill must follow the same rule.
- **`trending-tab.ts`** — `SOURCE_LABELS` (`trakt`→`Trakt`, `tmdb`→`TMDB`,
  `seer`→`Seer`), the label to show on the expanded source-link pill.
- **`trending-item-status.ts`** — `isAvailable` / `isPending`; unchanged.
- **`shared/lib/api.ts:792`** — `already_tracked: boolean` stays on the type (still
  returned by the API); only its *rendering* is removed.

Toolchain: Tailwind CSS `^4.3.1`, lucide-react `^1.21.0`,
class-variance-authority `^0.7.1`, React `^19.2.7`. Tests: `vitest run`
(targeted: `npx vitest run src/features/trending`). Lint: `eslint .`.
Type/build: `tsc -b`.

## Assumptions and constraints

- **Target size = 32px / `h-8`** (user-selected) at the default density, scaling
  down at higher poster-per-row densities so the pills stay proportional to the
  cards. Density 5 uses 32px pills, density 6 uses 28px pills, density 7 uses 24px
  pills. At every density all three pills are perfect circles at rest, with icons
  centred and labels/text scaled to match.
- **All three expand** (user-selected): source link → `Trakt`/`TMDB`/`Seer`,
  status → short label, Add → `Add`. Each keeps its **own** hover/focus group
  (`group/link`, `group/status`, `group/add`) so only the hovered pill expands —
  this is the primary defence against the 7-per-row overlap: the two bottom pills
  can't be expanded simultaneously by hover.
- **Status stays a `role="img"` span** (non-interactive), so it expands on **hover
  only** (a span is not focus-visible); its full detail remains in
  `aria-label`/`title` for assistive tech. The visible label is deliberately short
  (`Available` / `In library` / `Requested` / `Processing` / `Partial` /
  `In progress`) to keep the expanded pill narrow.
- **No-overlap belt-and-braces:** cap each label's growth (`max-w-*`), keep labels
  short, and raise the hovered pill's stacking (`hover:z-10` / `focus-within:z-10`)
  so an expanded pill sits above its neighbour rather than being clipped by it.
- **DRY:** the reveal classes are extracted into one shared helper rather than
  copied three times (strict-review DRY rule). Because Tailwind needs literal
  `group-hover/<name>:` strings, the per-group classes are held in a **literal
  record keyed by group** — the same technique as `GRID_COLS`.
- **British English** in all new comments/docs. No commits (per CLAUDE.md).
- Keep the amber indicator's **dotted-circle identity** (the user named it): its
  resting state stays a dotted-border circle; on hover it expands into a
  dotted-border lozenge with the label.

## Progress tracker

- **Overall status:** Complete
- **Current phase:** Phase 3 (done)
- **Last updated:** 2026-07-06 — all phases implemented and verified.
- Phase 0 — Analysis & baseline: `[x]`
- Phase 1 — Shared pill primitive + status rework: `[x]`
- Phase 2 — Wire link + Add, remove Tracked, guarantee no overlap: `[x]`
- Phase 3 — Tests, lint, type-check, visual verification: `[x]`

## Phase 0: Analysis, safeguards and baseline

**Goal.** Confirm the green baseline before touching anything, so regressions are
attributable.

Likely files: none modified (read/verify only).

- [x] Confirm working tree matches `git status` (Trending files modified/untracked).
- [x] Run the targeted suite to record a green baseline:
      `npx vitest run src/features/trending`.
- [x] Run `eslint .` and `tsc -b` once to record any pre-existing warnings so new
      ones are distinguishable.
- [x] Grep to confirm `already_tracked` is rendered **only** in `TrendingCard.tsx`
      (already verified: type at `api.ts:792`, render at `TrendingCard.tsx:77`) so
      removing the badge cannot break another consumer.

### Verification

- Baseline test run passes (55 tests).
- `already_tracked` has exactly one render site (`TrendingCard.tsx:77`).

### Notes

`git status --short` showed the expected Trending files as modified/untracked.
Targeted suite, ESLint and `tsc -b` were all green before any edits, so the
baseline is clean.

## Phase 1: Shared pill primitive and status-indicator rework

**Goal.** Introduce one shared reveal helper and rebuild `TrendingStatusIndicator`
as an `h-8` hover-expanding pill, preserving green/amber identity and accessibility.

Likely files:
- `frontend/src/features/trending/components/poster-pill.tsx` *(new)*
- `frontend/src/features/trending/components/TrendingStatusIndicator.tsx`

Steps:

- [x] **Create `poster-pill.tsx`** exporting:
  - `type PillGroup = "link" | "status" | "add"`.
  - `PILL_SHELL` — the shared container recipe matching `Button size="sm"` metrics
    so every pill is exactly `h-8`:
    `"inline-flex h-8 min-w-8 items-center justify-center rounded-full shadow-sm transition-all outline-none [&_svg]:size-4 motion-reduce:transition-none"`.
  - A `PillLabel` component rendering the collapsing label span. It takes
    `{ group, side, children }` where `side` (`"left" | "right"`) sets which side of
    the icon the label sits (label-before-icon for right-anchored pills, after for
    left-anchored), applied via the label's own `pr-1`/`pl-1` (clipped to nothing at
    `max-w-0`, so no gap-cancelling negative margins are needed):
    ```tsx
    "max-w-0 overflow-hidden whitespace-nowrap opacity-0 transition-all duration-200 motion-reduce:transition-none"
    ```
    plus the per-group reveal, stored as a **literal record** (Tailwind-JIT-safe):
    ```ts
    const REVEAL: Record<PillGroup, string> = {
      link:   "group-hover/link:max-w-24 group-hover/link:opacity-100 group-focus-visible/link:max-w-24 group-focus-visible/link:opacity-100",
      status: "group-hover/status:max-w-24 group-hover/status:opacity-100",
      add:    "group-hover/add:max-w-24 group-hover/add:opacity-100 group-focus-visible/add:max-w-24 group-focus-visible/add:opacity-100",
    }
    ```
    (Status omits the `focus-visible` pair — a `span` is not focusable; hover only.)
  - British-English doc comment explaining the own-group-per-pill rule and the
    literal-record/Tailwind-JIT constraint (mirror the `GRID_COLS` comment).
- [x] **Rework `TrendingStatusIndicator.tsx`:**
  - Add a `shortPendingLabel(item)` helper returning the concise visible label:
    the Seer label when present (`Requested`/`Processing`/`Partial`), else
    `"In progress"` (replacing the long `"In library, media not downloaded"` for the
    *visible* pill only). Keep the existing `pendingLabel()` for the full
    `title`/`aria-label`.
  - **Available branch:** wrap in `PILL_SHELL` + `group/status`, `bg-emerald-500`
    `text-white`, keep `role="img"`, `aria-label`/`title` = detail
    (`In library`/`Available`). Render `<CheckIcon aria-hidden />` then
    `<PillLabel group="status" side="right">{detail}</PillLabel>`. Add
    `hover:z-10`.
  - **Pending branch:** `PILL_SHELL` + `group/status` +
    `border-2 border-dotted border-amber-500 bg-background/85 backdrop-blur-sm`
    (preserves the dotted-circle identity; resting state is an empty dotted circle
    at `min-w-8 h-8`), `text-amber-600 dark:text-amber-500`. `aria-label`/`title` =
    `pendingLabel(item)` (full), visible `<PillLabel group="status" side="right">`
    = `shortPendingLabel(item)`. Add `hover:z-10`.
  - Keep the `return null` fall-through unchanged.

### Verification

- `npx vitest run src/features/trending/components/TrendingStatusIndicator.test.tsx`
  passes after the test updates in Phase 3 (the existing `bg-emerald-500`,
  `border-amber-500`, `border-dotted` and `getByLabelText` assertions must still
  hold — the class identities and full aria-labels are deliberately preserved).
- Resting indicator renders as a 32px circle; hovering reveals the short label.

### Notes

Created `frontend/src/features/trending/components/poster-pill.tsx` with
`PillGroup`, `PILL_SHELL` and `PillLabel`. The `REVEAL` literal record keeps the
Tailwind JIT classes intact. `TrendingStatusIndicator.tsx` now wraps both branches
in `PILL_SHELL`, preserves the existing `bg-emerald-500` / `border-amber-500` /
`border-dotted` identities, and exposes short visible labels while keeping the
full text in `aria-label`/`title`.

## Phase 2: Wire the link and Add pills, remove Tracked, guarantee no overlap

**Goal.** Bring the source-link and Add pills to the same `h-8` shell + reveal,
delete the Tracked badge, and lock in the no-overlap behaviour at 7-per-row.

Likely files:
- `frontend/src/features/trending/components/TrendingCard.tsx`
- `frontend/src/features/trending/components/AddToListControl.tsx`

Steps:

- [x] **Remove the Tracked badge** from `TrendingCard.tsx`: delete the
      `item.already_tracked ? <Badge …>Tracked</Badge> : null` block and the now-unused
      `Badge` import. Update the component doc comment (drop the "Tracked badge"
      clause). Leave `already_tracked` on the API type untouched.
- [x] **Source-link pill** (`TrendingCard.tsx`): replace the `p-1`/`size-4` recipe on
      the `<a>` with `cn(PILL_SHELL, "group/link bg-background/85 text-muted-foreground backdrop-blur-sm hover:text-foreground hover:z-10 focus-visible:z-10 px-2.5")`.
      Keep `ExternalLinkIcon size-4`; because the pill is `right-1`-anchored it grows
      **leftward**, so place the label **before** the icon:
      `<PillLabel group="link" side="left">{sourceLabel}</PillLabel><ExternalLinkIcon … />`.
      Retain `title`/`aria-label` for the tooltip and screen-reader text.
- [x] **Add pill** (`AddToListControl.tsx`): refactor `AddButtonBody` to reuse
      `PillLabel group="add" side="left"` instead of the hand-rolled span, so the
      three pills share one reveal implementation. Keep the solid-black `ADD_BUTTON`
      styling and `Button size="sm"` (already `h-8`); add `rounded-full` and
      `hover:z-10 focus-visible:z-10` to `ADD_BUTTON` so it matches the pill family
      and stacks above a neighbour when expanded.
- [x] **No-overlap check at 7/row:** with each pill on its own group, only one
      expands per hover. Confirm the two bottom pills, each capped at `max-w-24` and
      raised via `z-10`, never visually collide at `lg:grid-cols-7` (see Phase 3
      visual step). Tune `max-w-*` down if a real label overruns the card centre.

### Verification

- `TrendingCard` renders exactly three corner pills (no Tracked badge).
- Each pill is `h-8`; hovering any one expands only that pill.

### Notes

Removed the `Badge` import and the top-left Tracked badge from
`TrendingCard.tsx`. The source link now uses `PILL_SHELL` with `group/link` and a
`PillLabel` that grows leftward. `AddToListControl.tsx` uses `PillLabel` for the
reveal and adds `rounded-full` plus z-index stacking to `ADD_BUTTON`. Padding and
icon sizes are density-aware so every pill is a perfect circle at rest and the
icon is centred. The label padding is applied only while expanded so the
collapsed span contributes zero width and the resting shape stays circular.
Visual checks at 7-per-row confirmed the bottom pills do not collide.

## Phase 3: Tests, lint, type-check and visual verification

**Goal.** Update co-located tests for the new behaviour and prove the change end to
end.

Likely files:
- `frontend/src/features/trending/components/TrendingCard.test.tsx`
- `frontend/src/features/trending/components/TrendingStatusIndicator.test.tsx`
- `frontend/src/features/trending/components/AddToListControl.test.tsx` *(likely
  unchanged — still asserts `getByText("Add")`; confirm it passes)*

Steps:

- [x] **`TrendingCard.test.tsx`:** replace the `"shows a Tracked badge …"` test with
      one asserting the badge is **absent** even when `already_tracked: true`
      (`expect(screen.queryByText("Tracked")).not.toBeInTheDocument()`). Keep the
      existing status-indicator assertions (`bg-emerald-500`, `border-amber-500`,
      `border-dotted`) — they still hold. Optionally add a test that the source-link
      pill exposes its source label (`getByText("TMDB")` for a tmdb item, present in
      the DOM for the reveal to animate).
- [x] **`TrendingStatusIndicator.test.tsx`:** keep all class/aria assertions (they
      are preserved by design). Add: the short visible label is present in the DOM
      for a pending item (e.g. `getByText("Processing")` for `seer_status: 3`, and
      `getByText("In progress")` for the library-record-without-media case) so the
      reveal has content. The full `aria-label` assertions stay
      (`In library, media not downloaded`, `Processing`, …).
- [x] **`AddToListControl.test.tsx`:** re-run; `getByText("Add")` and the disabled/
      pending/menu behaviours must still pass unchanged.
- [x] Run the full targeted suite, lint, and type-check.
- [x] **Visual verification** (required — this is user-facing CSS): `npm run dev`,
      open Trending, set the density toggle to **7**, and confirm:
      all four corners now read as one 32px pill family; no Tracked badge; hovering
      each pill (link, status, Add) reveals its label; and at 7-per-row the bottom
      pills never overlap (only the hovered one expands and it stacks above its
      neighbour). Check both light and dark themes and `prefers-reduced-motion`.

### Verification

- `npx vitest run src/features/trending` — all green (56 tests).
- `npx eslint .` — clean.
- `npx tsc -b` — clean.
- Manual: verified at densities 5, 6 and 7 in dark and light themes; all three
  pill types are identically-sized circles at rest, icons are centred, and labels
  expand on hover without overlapping or clipping.

### Notes

Updated `TrendingCard.test.tsx` to assert the Tracked badge is absent and that
the source label is present in the DOM for the reveal. Added short-label
assertions to `TrendingStatusIndicator.test.tsx`. `AddToListControl.test.tsx`
passed unchanged. Full targeted suite, ESLint and `tsc -b` are all green.

## Verified results

- `npx vitest run src/features/trending` — passed (56 tests, 5 test files).
- `npx eslint .` — passed (exit 0, no warnings).
- `npx tsc -b` — passed (exit 0).
- Manual 7-per-row visual check — passed:
  - Navigated to `http://localhost:5173/trending`.
  - Set density toggle to **7** (`lg:grid-cols-7`).
  - Dark theme baseline: all cards show uniform 32px pills in three corners; no
    Tracked badge; green ticks / amber dotted circles / black Add pills read as
    one family.
  - Hover checks at 7-per-row:
    - Source-link pill expands to show source label (e.g. "Trakt"), growing
      leftward without clipping.
    - Status pill expands to show short label (e.g. "In library", "In progress"),
      growing rightward.
    - Add pill expands to show "Add +", growing leftward.
    - In each case only the hovered pill expands; the two bottom pills never
      collide; `hover:z-10` keeps the expanded pill above its neighbour.
  - Light theme: same checks pass; amber dotted pill identity preserved.
  - `prefers-reduced-motion`: emulated via stylesheet; labels still expand
    instantly and remain readable.

## Risks

- **Tailwind JIT purge.** Interpolated `group-hover/<name>:` classes will not compile.
  Mitigation: the literal-record technique (Phase 1) — mirror `GRID_COLS`. Verify by
  inspecting the rendered pill in the browser, not just the test DOM (jsdom does not
  evaluate Tailwind).
- **Label overflow at 7/row.** A long real label plus a capped `max-w` could still
  reach the card centre. Mitigation: short visible labels + `max-w-24` + `z-10`; tune
  `max-w-*` down during the visual step if needed.
- **Focusability of the status pill.** It remains a non-interactive `role="img"`
  span, so it expands on hover only; keyboard users rely on the preserved
  `aria-label`. If keyboard reveal is later wanted, promote it to a focusable
  element — out of scope here.
- **Test brittleness.** Some existing tests assert exact utility classes
  (`bg-emerald-500`, `border-dotted`). The plan preserves those class identities to
  avoid churn; if a class must change, update the assertion in the same commit-scope.
- **`already_tracked` now unrendered.** The field stays on the API type and payload;
  only its badge is removed. No functional data loss — purely presentational.
