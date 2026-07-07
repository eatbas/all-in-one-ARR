# Implementation Plan

## Objective

Fix the Trending poster overlay pills so the three controls are visually consistent:

- Source-link, status, and add controls must all collapse to the same perfect circular shape for the active density.
- Icons inside the pills must be the same visual size and centred on both axes.
- The status control must not become a different shape when it is pending, requested, processing, partial, available, or in-library.
- Hover/focus reveal text must fit inside the card and avoid clipping awkwardly, overflowing over neighbouring controls, or producing unreadable text.

This is a focused UI plan for the Trending card pill controls only. It must not continue the previously interrupted broad infrastructure apply-plan work.

## Current state

- Branch: `main`.
- There are many existing local changes from the interrupted previous apply-plan work and separate Trending work. Treat them as pre-existing unless this pill fix explicitly touches the same files.
- Relevant files inspected:
  - `frontend/src/features/trending/components/poster-pill-variants.ts`
  - `frontend/src/features/trending/components/poster-pill.tsx`
  - `frontend/src/features/trending/components/TrendingCard.tsx`
  - `frontend/src/features/trending/components/AddToListControl.tsx`
  - `frontend/src/features/trending/components/TrendingStatusIndicator.tsx`
  - `frontend/src/features/trending/components/TrendingCard.test.tsx`
  - `frontend/src/features/trending/components/AddToListControl.test.tsx`
  - `frontend/src/features/trending/components/TrendingStatusIndicator.test.tsx`
- Current likely root causes:
  - `pillShell()` uses `h-* min-w-*` rather than a fixed square collapsed size, so callers can change the collapsed shape with padding.
  - `TrendingCard.tsx` adds `sourceLinkPadding()`, making the source-link pill a different shape from the other controls.
  - `AddToListControl.tsx` uses a separate `addButtonClasses()` recipe with `has-[>svg]:px-*`, so the add control does not share the exact shell geometry.
  - `TrendingStatusIndicator.tsx` uses the shared shell, but pending status uses `border-2 border-dotted` and currently renders no icon, so it looks different from the other icon pills.
  - `PillLabel` uses `max-w-24` for every label, which can exceed the available space on small/dense cards. Some labels, especially `"In progress"` or source labels, can fail to fit cleanly.
- Context7 documentation consulted:
  - Tailwind CSS v4 docs for `size-*` square sizing utilities, `rounded-full`, hover/focus variants, overflow, whitespace, and max-width behaviour.
- Project versions relevant to implementation:
  - Tailwind CSS `4.3.1`
  - React `19.2.7`
  - lucide-react `1.21.0`

## Assumptions and constraints

- Do not implement during this `create-plan` invocation.
- Preserve existing public component props: `TrendingCard`, `AddToListControl`, and `TrendingStatusIndicator` should keep their current `item` and `density` props.
- Preserve existing accessibility semantics:
  - Source link keeps a descriptive `aria-label`.
  - Add button keeps `aria-label="Add to a list"`.
  - Status indicator keeps a meaningful `aria-label` and `title`.
- Use lucide icons rather than manually drawn SVG icons.
- Keep every collapsed pill square and circular by default; expanded hover/focus state can become a rounded lozenge.
- Avoid viewport-scaled font sizes. Use fixed Tailwind text classes already established in the component.
- Do not touch unrelated Trending data, API, query, or backend code.
- Do not overwrite user-owned unrelated changes. Read changed Trending files immediately before editing if this plan is later applied.

## Progress tracker

- Overall status: Complete.
- Current phase: Complete.
- Last updated: 2026-07-07.
- Implementation owner notes: Applied via apply-review on 2026-07-07.

## Phase 0: Baseline and Visual Reproduction

Goal: Capture the current pill layout problem and establish exact target behaviour before editing.

Likely files or modules:

- `frontend/src/features/trending/components/poster-pill-variants.ts`
- `frontend/src/features/trending/components/poster-pill.tsx`
- `frontend/src/features/trending/components/TrendingCard.tsx`
- `frontend/src/features/trending/components/AddToListControl.tsx`
- `frontend/src/features/trending/components/TrendingStatusIndicator.tsx`
- `frontend/src/features/trending/components/*.test.tsx`
- Existing screenshot artefacts such as `trending-density-*-*.png`

Checklist:

- [x] Record `git status --short` before editing and identify which Trending files already contain user-owned changes.
- [x] Open the current Trending page or component test harness at densities `5`, `6`, and `7`.
- [x] Capture or inspect screenshots for:
  - collapsed source-link pill
  - collapsed status pill
  - collapsed add pill
  - source-link hover/focus reveal
  - status hover/focus reveal
  - add hover/focus reveal
- [x] Confirm which labels fail to fit. Test at least `TMDB`, `Trakt`, `Seer`, `Available`, `In library`, `Requested`, `Processing`, `Partial`, `In progress`, and `Add`.
- [x] Define the target collapsed dimensions by density:
  - density `5`: one fixed circular size
  - density `6`: one fixed circular size
  - density `7`: one fixed circular size
- [x] Define a single target icon size per density, and apply it through one shared helper.

Verification:

- [x] Baseline screenshots or visual notes are recorded in `## Verified results`.
- [x] The target sizes are written in Phase 0 notes before implementation begins.

Notes:

Baseline reproduced from the existing Trending pill implementation and screenshot
artefacts. Target collapsed dimensions are `32x32` for density `5`, `28x28` for
density `6`, and `24x24` for density `7`; icon sizes are `size-4`, `size-3.5`,
and `size-3` respectively.

## Phase 1: Standardise Pill Geometry and Icon Slots

Goal: Make all three collapsed controls share one square/circular shell and one centred icon slot.

Likely files or modules:

- `frontend/src/features/trending/components/poster-pill-variants.ts`
- `frontend/src/features/trending/components/poster-pill.tsx`
- `frontend/src/features/trending/components/TrendingCard.tsx`
- `frontend/src/features/trending/components/AddToListControl.tsx`
- `frontend/src/features/trending/components/TrendingStatusIndicator.tsx`

Checklist:

- [x] Replace the current `h-* min-w-*` shell sizing with fixed collapsed `size-*` dimensions in the shared pill helper.
- [x] Add a shared icon-slot helper, for example `pillIconSlot(density)`, that provides a fixed square flex/grid centre for every pill icon.
- [x] Keep `pillIcon(density)` for the SVG size, but ensure every icon is rendered inside the same icon slot.
- [x] Remove `sourceLinkPadding()` from `TrendingCard.tsx`; the source-link pill should not add custom padding in its collapsed state.
- [x] Replace `AddToListControl.tsx`'s custom size/padding recipe with the same shared pill shell and icon slot.
- [x] Ensure `Button` defaults do not add conflicting icon padding. If necessary, add explicit `px-0 gap-0` or equivalent classes through the add control only.
- [x] Make the status indicator render an icon in every visible state:
  - `CheckIcon` for available / in-library.
  - A lucide status icon such as `ClockIcon`, `CircleDashedIcon`, or `LoaderCircleIcon` for requested / processing / partial / in-progress.
- [x] Keep pending status visually amber, but make its collapsed outer geometry identical to the source/add pills.
- [x] Ensure border styling does not visually shrink or offset the icon. Use `box-border`, an inset ring, or a wrapper if needed.

Verification:

- [x] Unit tests assert the source link, add control, and status indicator receive the same collapsed shell class for a given density.
- [x] Unit tests assert the status indicator renders an icon for pending states as well as available states.
- [x] `cd frontend && npm run test:types -- --pretty false` passes.
- [x] `cd frontend && npm run lint` passes.

Notes:

Implemented shared `size-*` pill shells, shared icon slots, caller-independent
source/add/status geometry, and a pending status icon. The add button keeps the
existing dropdown trigger behaviour while neutralising conflicting button
padding with explicit `px-0` / `has-[>svg]:px-0` classes.

## Phase 2: Fix Hover/Focus Text Fitting

Goal: Make hover/focus reveal labels readable and bounded without breaking the circular collapsed state.

Likely files or modules:

- `frontend/src/features/trending/components/poster-pill.tsx`
- `frontend/src/features/trending/components/poster-pill-variants.ts`
- `frontend/src/features/trending/components/TrendingCard.tsx`
- `frontend/src/features/trending/components/AddToListControl.tsx`
- `frontend/src/features/trending/components/TrendingStatusIndicator.tsx`

Checklist:

- [x] Replace the single `max-w-24` reveal width with density-aware reveal widths.
- [x] Use side-aware constraints:
  - left-side status pill can expand rightward, but must not collide with the add pill.
  - right-side source and add pills can expand leftward, but must stay inside the poster card.
- [x] Keep `whitespace-nowrap` for short labels, but truncate with `overflow-hidden text-ellipsis` when a label is too long.
- [x] Consider shorter visible labels where necessary while preserving precise `title` and `aria-label`; for example keep `"In progress"` visible but keep full `"In library, media not downloaded"` in assistive/hover metadata.
- [x] Ensure hover/focus variants exist for keyboard users as well as mouse users. The current status reveal lacks focus-visible support; add a focus path if the status element is focusable, or keep the label visible only on hover if it remains non-interactive.
- [x] Keep text inside the expanding pill vertically centred with the icon.
- [x] Avoid negative margins or layout tricks that make text overlap poster content or neighbouring controls.

Verification:

- [x] Component tests assert all expected label text remains in the DOM.
- [x] Component tests assert labels carry truncation/overflow classes or shared reveal classes.
- [x] Visual verification confirms hover/focus text fits at densities `5`, `6`, and `7` for the longest expected labels.

Notes:

Implemented density-aware reveal widths, truncation classes, and side-aware
label padding. The non-interactive status indicator remains hover-only; source
and add retain focus-visible reveal paths for keyboard users.

## Phase 3: Regression Tests and Visual QA

Goal: Prove the fix works across density modes, mouse hover, and keyboard focus.

Likely files or modules:

- `frontend/src/features/trending/components/TrendingCard.test.tsx`
- `frontend/src/features/trending/components/AddToListControl.test.tsx`
- `frontend/src/features/trending/components/TrendingStatusIndicator.test.tsx`
- Optional visual screenshot artefacts under the repository root or a temporary path

Checklist:

- [x] Add or update tests for equal density classes across all three controls.
- [x] Add tests for density `5`, `6`, and `7`, not just the default.
- [x] Add tests for the pending status icon path.
- [x] Add tests for hover label text presence and truncation class usage.
- [x] Run the narrow component tests:
  - `cd frontend && npm test -- src/features/trending/components/TrendingCard.test.tsx src/features/trending/components/AddToListControl.test.tsx src/features/trending/components/TrendingStatusIndicator.test.tsx`
- [x] Run frontend verification:
  - `cd frontend && npm run lint`
  - `cd frontend && npm run test:types -- --pretty false`
  - `cd frontend && npm test`
- [x] If a browser harness is available, run Playwright or in-app browser screenshots at mobile and desktop widths, including hover states for all three pills.

Verification:

- [x] Test command output is recorded in `## Verified results`.
- [x] Screenshot paths or manual visual QA notes are recorded in `## Verified results`.
- [x] No unrelated files are modified.

Notes:

Added component coverage for equal shell classes, density `5` / `6` / `7`, icon
slots, pending status icons, and reveal label truncation. Ran full frontend
verification and Playwright browser checks.

## Verified results

This section must be updated during implementation with exact commands and outcomes.

- Planning-only run:
  - [x] Implemented via `apply-review` on 2026-07-07.
- Baseline screenshots / visual notes:
  - [x] Existing baseline screenshots were inspected, then updated hover-state
    screenshots were captured for densities `5`, `6`, and `7`:
    `trending-density-5-link-hover.png`,
    `trending-density-5-status-hover.png`,
    `trending-density-5-add-hover.png`,
    `trending-density-6-link-hover.png`,
    `trending-density-6-status-hover.png`,
    `trending-density-6-add-hover.png`,
    `trending-density-7-link-hover.png`,
    `trending-density-7-status-hover.png`,
    `trending-density-7-add-hover.png`.
- Targeted component tests:
  - [x] `cd frontend && npm test -- src/features/trending/components/TrendingCard.test.tsx src/features/trending/components/AddToListControl.test.tsx src/features/trending/components/TrendingStatusIndicator.test.tsx` passed: 3 files, 42 tests.
- Frontend lint/type/test verification:
  - [x] `cd frontend && npm run test:types -- --pretty false` passed.
  - [x] `cd frontend && npm run lint` passed.
  - [x] `cd frontend && npm test` passed: 46 files, 534 tests.
- Visual QA:
  - [x] Playwright with mocked Trending API data confirmed collapsed source,
    add, and status pills and their icon slots are all `32x32`, `28x28`, and
    `24x24` at densities `5`, `6`, and `7` respectively. Hover expansion was
    also verified at every density: link/status/add widths were `70/98/58`,
    `63/89/53`, and `57/76/47` pixels for densities `5`, `6`, and `7`.

## Risks

- `Button` component defaults may inject padding through variant classes. The add pill may need explicit classes to neutralise button defaults without affecting other buttons.
- The status indicator is currently a non-interactive `span`; focus-visible reveal may not apply unless it becomes focusable. Do not add tab stops purely for decoration unless accessibility semantics justify it.
- Dotted borders can make the pending status pill appear smaller than filled pills. Prefer an inset ring or consistent box sizing if the visual result still looks off.
- Long labels can never fully fit on very dense poster cards if all controls expand simultaneously. The implementation should truncate gracefully and rely on `title` / `aria-label` for full text.
- Current Trending files are already modified and partly untracked. Re-read them before applying this plan to avoid overwriting user-owned work.
