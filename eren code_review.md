### Summary
- The requested pill-fix plan is not complete. `plan_request_codex.md` still records `Overall status: Not started`, every checklist item is unchecked, and `## Verified results` is still pending.
- The current Trending component state is not safe to merge: TypeScript fails because callers pass a `side` prop to `PillLabel`, but `PillLabel` no longer accepts that prop.
- The visual objective is still unmet. Source, add, and status controls continue to use separate sizing/padding paths, the pending status pill still has no icon, and reveal text still uses a single `max-w-24` recipe rather than density-aware bounded text.
- Context7 Tailwind CSS documentation was consulted for the relevant `size-*`, flex centring, overflow/truncation, and hover/focus utility behaviour before this audit.

### Findings
[SEVERITY: BLOCKER] frontend/src/features/trending/components/poster-pill.tsx:14
`PillLabel` no longer accepts a `side` prop, but the current callers still pass `side` at `AddToListControl.tsx:45`, `TrendingCard.tsx:104`, and `TrendingStatusIndicator.tsx:68` / `:86`. `npm run test:types -- --pretty false` fails with TS2322, so the current tree is not buildable.
Fix: Either remove every `side` prop from the callers or restore `side` in `PillLabel`'s props and use it consistently; then rerun `cd frontend && npm run test:types -- --pretty false`.

[SEVERITY: MAJOR] plan_request_codex.md:56
The plan has not been applied or updated. It still says `Overall status: Not started`, all phase checkboxes are unchecked, and `## Verified results` is pending, so the repository state cannot be considered verified against the plan.
Fix: Apply the plan phases, update each checklist item as it is completed, and record exact command output plus visual QA notes under `## Verified results`.

[SEVERITY: MAJOR] frontend/src/features/trending/components/poster-pill-variants.ts:6
`pillShell()` still uses `h-* min-w-*` sizing rather than the planned fixed square collapsed `size-*` classes. That allows caller padding to change the collapsed pill shape, which is the exact visual defect the plan is meant to remove.
Fix: Replace the shell sizing with fixed density classes such as `size-8`, `size-7`, and `size-6`, and introduce a shared `pillIconSlot(density)` helper that centres every SVG in the same fixed square slot.

[SEVERITY: MAJOR] frontend/src/features/trending/components/TrendingCard.tsx:20
`sourceLinkPadding()` remains in place and is still applied to the source pill at `TrendingCard.tsx:101`. This keeps source-link geometry separate from status/add geometry and can make the collapsed source pill wider than the others.
Fix: Remove `sourceLinkPadding()` and make the source link rely only on the shared pill shell plus shared icon slot in its collapsed state.

[SEVERITY: MAJOR] frontend/src/features/trending/components/AddToListControl.tsx:23
`AddToListControl` still has its own `addButtonClasses()` recipe with `h-* min-w-* has-[>svg]:px-*`, duplicating and diverging from the shared pill helper. The add button can therefore render with different width, padding, and icon centring from the other controls.
Fix: Compose the add button from `pillShell(density)`, the shared icon slot, and explicit `px-0 gap-0` button overrides only where needed to neutralise the base button component.

[SEVERITY: MAJOR] frontend/src/features/trending/components/TrendingStatusIndicator.tsx:74
The pending status path still renders no icon and uses `border-2 border-dotted`, while the available path renders a check icon. This violates the plan requirement that every visible status state has an icon and the same collapsed outer geometry.
Fix: Render a lucide pending icon, such as `ClockIcon` or `LoaderCircleIcon`, inside the shared icon slot for requested, processing, partial, and in-progress states; use inset ring or box-border styling if the amber outline must remain visible without changing perceived size.

[SEVERITY: MAJOR] frontend/src/features/trending/components/poster-pill-variants.ts:39
The reveal classes still hard-code `max-w-24` for every group and density, and the status reveal has no focus-visible path. That does not satisfy the plan's bounded, density-aware hover/focus text requirement and can still overflow or clip awkwardly on dense cards.
Fix: Replace `REVEAL` with a helper that returns density-aware max widths and truncation classes, add `text-ellipsis`, and only add focus-visible behaviour for elements that are actually focusable.

[SEVERITY: MAJOR] frontend/src/features/trending/components/TrendingStatusIndicator.test.tsx:41
The relevant tests do not assert the plan's geometry contract. They check labels and some colour classes, but they do not prove equal collapsed shell classes, shared icon slots, pending-status icon rendering, density `5` / `6` / `7` coverage, or truncation/reveal class usage.
Fix: Add targeted component tests for equal density classes across source/add/status controls, pending and available status icons, all three densities, and label overflow/truncation classes.

### Structural and DRY issues
- `frontend/src/features/trending/components/poster-pill-variants.ts`, `frontend/src/features/trending/components/TrendingCard.tsx`, and `frontend/src/features/trending/components/AddToListControl.tsx` still split pill sizing across three places: `SIZE`, `sourceLinkPadding()`, and `addButtonClasses()`. Extract all collapsed geometry and icon-slot behaviour into the shared pill helper and let each caller contribute only colour, position, and accessibility attributes.
- `frontend/src/features/trending/components/TrendingStatusIndicator.tsx` has two separate render branches whose structural differences affect visual geometry. Extract a small shared status pill body that always renders the icon slot and label, with only icon and colour classes varying by state.

### Required actions before PR
- Fix the `PillLabel` prop mismatch and make `cd frontend && npm run test:types -- --pretty false` pass.
- Apply Phase 1 by using fixed `size-*` collapsed shells and a shared centred icon slot for source, add, and status controls.
- Remove `sourceLinkPadding()` and replace `addButtonClasses()` sizing with the shared pill helper.
- Add a pending status icon and keep pending, available, in-library, requested, processing, partial, and in-progress status states on the same outer geometry.
- Replace `max-w-24` reveal classes with density-aware bounded reveal/truncation classes.
- Add tests for equal pill geometry, icon rendering, density `5` / `6` / `7`, and reveal text truncation.
- Update `plan_request_codex.md` checkboxes and `## Verified results` with exact commands and visual QA notes after implementation.
- Run the full planned verification after the blocker is fixed: narrow component tests, lint, type checking, frontend tests, and visual QA screenshots.
This must not be merged in its current form.

### Verification plan
- Ran `cd frontend && npm test -- src/features/trending/components/TrendingCard.test.tsx src/features/trending/components/AddToListControl.test.tsx src/features/trending/components/TrendingStatusIndicator.test.tsx`: passed, 3 files and 32 tests.
- Ran `cd frontend && npm run lint`: passed.
- Ran `cd frontend && npm run test:types -- --pretty false`: failed with TS2322 because `PillLabel` does not accept the `side` prop passed by `AddToListControl.tsx`, `TrendingCard.tsx`, and `TrendingStatusIndicator.tsx`.
- Skipped `cd frontend && npm test` and browser screenshot QA because the type-check blocker makes the current implementation non-mergeable and the plan is plainly not applied.

## Verification pass
- RESOLVED - not reproducible: the `PillLabel` `side`-prop blocker was no longer present in the current source when remediation began. The current implementation keeps `side` as an explicit `PillLabel` prop and all call sites type-check.
- Fixed: shared pill geometry now uses fixed `size-*` collapsed shells and a shared `pillIconSlot(density)` helper.
- Fixed: `sourceLinkPadding()` was removed and the source pill uses `pillShell(density)`, `PILL_EXPAND.link`, and the shared icon slot.
- Fixed: `AddToListControl` no longer has a separate `h-* min-w-* has-[>svg]:px-*` size recipe; it composes the shared pill shell and explicit button padding overrides.
- Fixed: pending status now renders a lucide `ClockIcon` in the same icon slot as available status, and amber styling uses an inset ring so the outer geometry stays consistent.
- Fixed: reveal labels now use density-aware bounded widths plus `overflow-hidden text-ellipsis whitespace-nowrap`.
- Fixed: tests now assert equal shell/icon-slot classes, density `5` / `6` / `7`, pending status icon rendering, and reveal label truncation.
- Updated: `plan_request_codex.md` now records completed checklist items, exact verification commands, and Playwright screenshot/geometry results.
- Verified: `cd frontend && npm run test:types -- --pretty false` passed.
- Verified: `cd frontend && npm run lint` passed.
- Verified: `cd frontend && npm test -- src/features/trending/components/TrendingCard.test.tsx src/features/trending/components/AddToListControl.test.tsx src/features/trending/components/TrendingStatusIndicator.test.tsx` passed: 3 files, 42 tests.
- Verified: `cd frontend && npm test` passed: 46 files, 534 tests.
- Verified: Playwright with mocked Trending API data confirmed collapsed source, add, and status pills and their icon slots are all `32x32`, `28x28`, and `24x24` at densities `5`, `6`, and `7` respectively. Hover expansion was also verified at every density: link/status/add widths were `70/98/58`, `63/89/53`, and `57/76/47` pixels for densities `5`, `6`, and `7`.
