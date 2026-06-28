# Implementation Plan

## Objective

Add small information icons beside settings controls so users can hover or focus each icon to understand what the adjacent toggle, button, select, or field does. Keep the behaviour accessible, keyboard reachable, and consistent with the existing React, Radix UI, Tailwind, and lucide-react patterns.

## Current state

- The frontend is a Vite React application under `frontend/`.
- Exact lockfile versions relevant to this work:
  - `react` and `react-dom`: `19.2.7`
  - `radix-ui`: `1.6.0`
  - `lucide-react`: `1.21.0`
  - `@testing-library/react`: `16.3.2`
  - `@testing-library/user-event`: `14.6.1`
  - `vitest`: `4.1.9`
- Context7 documentation was consulted for Radix Tooltip composition and lucide React icon usage.
  - Radix Tooltip guidance confirms `Tooltip.Provider`, `Tooltip.Root`, `Tooltip.Trigger asChild`, portal-backed `Tooltip.Content`, and hover/focus behaviour.
  - Context7 only listed lucide docs at `0.547.0`, while the project pins `lucide-react` `1.21.0`; use the docs only for compatible import and prop patterns already present in this repo.
- `frontend/src/main.tsx` already wraps the app in `TooltipProvider delayDuration={200}`.
- `frontend/src/shared/components/ui/tooltip.tsx` already exposes `Tooltip`, `TooltipTrigger`, `TooltipContent`, and `TooltipProvider`.
- Settings controls are currently spread across:
  - `frontend/src/features/settings/Settings.tsx`
  - `frontend/src/features/findarr/tabs/Settings.tsx`
  - `frontend/src/features/list-syncarr/tabs/ListSettings.tsx`
  - `frontend/src/features/list-syncarr/components/trakt-list-selector.tsx`
  - `frontend/src/features/bandwidth-controllarr/tabs/BandwidthSettings.tsx`
  - Convenience duplicates in `frontend/src/features/findarr/tabs/Status.tsx` and `frontend/src/features/bandwidth-controllarr/tabs/Status.tsx`
- Existing tests already cover the affected settings surfaces:
  - `frontend/src/features/settings/Settings.test.tsx`
  - `frontend/src/features/findarr/Findarr.test.tsx`
  - `frontend/src/features/list-syncarr/tabs/ListSettings.test.tsx`
  - `frontend/src/features/list-syncarr/components/trakt-list-selector.test.tsx`
  - `frontend/src/features/bandwidth-controllarr/tabs/BandwidthSettings.test.tsx`
  - `frontend/src/features/findarr/tabs/Status.test.tsx`
  - `frontend/src/features/bandwidth-controllarr/tabs/Status.test.tsx`

## Assumptions and constraints

- This plan intentionally stops before implementation, per the `create-plan` request.
- Do not add new dependencies. Reuse the existing Radix tooltip primitive and lucide icons.
- Preserve current form semantics and accessible names for inputs, selects, switches, and buttons. The new help icon must not become part of the adjacent control's accessible name.
- Tooltip triggers must be keyboard focusable and labelled, not hover-only. Use an icon button with an accessible label such as `Explain Status check interval`.
- Keep visible helper text where it already provides useful persistent context. The icon tooltip should supplement or consolidate explanations without removing critical information from screen-reader users.
- Do not expose secrets or actual credential values in tooltip content.
- Use British English spelling in new comments, documentation, and user-facing explanatory text where wording allows it.
- Generated plan and review artefacts must not be committed. If future execution creates generated files, verify they are ignored by `.gitignore`.

## Progress tracker

- Overall status: Complete
- Current phase: Completed
- Last updated state: Implemented settings help icons, added coverage, and completed automated plus Playwright verification

## Phase 0: Accessibility and Component Design

Goal: Define one reusable help-icon component and a concise tooltip copy map before touching settings screens.

Likely files or modules:

- `frontend/src/shared/components/settings-help.tsx` or `frontend/src/shared/components/ui/settings-help.tsx`
- `frontend/src/shared/components/settings-help.test.tsx` if a dedicated shared component test is added
- `frontend/src/shared/components/ui/tooltip.tsx` only if a small className or sideOffset adjustment is required

Checklist:

- [x] Create a reusable `SettingsHelp` component that composes existing `Tooltip`, `TooltipTrigger`, and `TooltipContent`.
- [x] Use a lucide info-style icon, preferably `InfoIcon` if available in the pinned package, with `className="size-4"` to match existing icon sizing.
- [x] Render the trigger as an icon-only `button` with `type="button"` and an explicit accessible label.
- [x] Use `TooltipTrigger asChild` so Radix attaches tooltip behaviour to the custom button, following the Context7 Radix docs.
- [x] Ensure the tooltip opens on hover and keyboard focus through Radix, and dismisses normally without custom global state.
- [x] Use constrained tooltip width such as `max-w-xs` or `max-w-sm` so longer explanations wrap cleanly on small screens.
- [x] Add or update a focused test proving the help icon is accessible by role/name and the tooltip content appears on hover or focus.

Verification:

- Run `cd frontend && npm test -- src/shared/components/ui/ui-primitives.test.tsx`.
- If a new shared test file is added, run `cd frontend && npm test -- src/shared/components/settings-help.test.tsx`.
- Run `cd frontend && npm run test:types`.

Notes:

Implemented `frontend/src/shared/components/settings-help.tsx` with `InfoIcon`, Radix `TooltipTrigger asChild`, a labelled icon-only button, and constrained tooltip content. Added `frontend/src/shared/components/settings-help.test.tsx` for accessible name, hover, and keyboard focus behaviour. No changes were required in `frontend/src/shared/components/ui/tooltip.tsx`.

## Phase 1: Add Help Icons to Settings Screens

Goal: Add help icons beside each settings control while preserving layout and current behaviour.

Likely files or modules:

- `frontend/src/features/settings/Settings.tsx`
- `frontend/src/features/findarr/tabs/Settings.tsx`
- `frontend/src/features/list-syncarr/tabs/ListSettings.tsx`
- `frontend/src/features/list-syncarr/components/trakt-list-selector.tsx`
- `frontend/src/features/bandwidth-controllarr/tabs/BandwidthSettings.tsx`
- `frontend/src/features/findarr/tabs/Status.tsx`
- `frontend/src/features/bandwidth-controllarr/tabs/Status.tsx`

Checklist:

- [x] Update the local `Field` helper in `Settings.tsx` to accept optional `helpText` and render the icon beside the label, not beside the saved-state hint.
- [x] Add help icons for Trakt fields: Client ID, Client secret, Connect/Re-connect Trakt, and Test connection.
- [x] Add help icons for service connection fields: URL, API key, and Test connection.
- [x] Add help icons for General settings: Status check interval and Appearance theme buttons.
- [x] Add help icons for Database actions: Clear activity log, Clear synced items and sync state, and Clear poster cache. Keep confirmation dialog descriptions intact.
- [x] Refactor Findarr `NumberInput` to accept a `helpText` prop and add icons for Enable Findarr, Interval, Hourly cap, Queue limit, Process app, Monitored only, Skip future, Missing per cycle, and Upgrades per cycle.
- [x] Add help icons to List-Syncarr settings for Add by Trakt URL, Remove list, discovered-list Sync switches, Remove from Trakt when available, and Sync interval.
- [x] Add help icons to Bandwidth-Controllarr settings for Check interval and Open `/metrics`.
- [x] Add help icons to duplicated settings controls in status tabs if they can change settings: Enable Findarr, Findarr run/reset buttons, and Enable bandwidth control.
- [x] Keep each tooltip close to the control label or command button so the visual relationship is obvious.
- [x] Avoid nesting cards or changing the page structure beyond local label/control rows.
- [x] Verify responsive layouts still fit at mobile width; use flex wrapping for label plus icon rows where needed.

Suggested tooltip copy map:

- Status check interval: "How often the dashboard refreshes connection status for configured integrations."
- Appearance: "Changes the dashboard colour mode only; it does not change backend behaviour."
- Trakt Client ID: "The public client identifier from your Trakt application."
- Trakt Client secret: "The private Trakt application secret. It is saved server-side and not shown again."
- Connect Trakt: "Starts Trakt device authorisation so this app can read and update your selected lists."
- Test connection: "Checks the saved credentials or token without changing settings."
- Service URL: "Base URL for this service, including protocol and port when required."
- Service API key: "API key saved server-side. Existing keys are never returned to the browser."
- Clear activity log: "Deletes activity history only; credentials and list configuration remain."
- Clear synced items and sync state: "Deletes mirrored list items and sync state so the next sync rebuilds them."
- Clear poster cache: "Deletes cached poster thumbnails. They are fetched again on demand."
- Enable Findarr: "Allows the scheduler to run bounded missing and upgrade searches."
- Findarr interval: "How often Findarr wakes up to run automatic searches."
- Hourly cap: "Maximum number of Findarr search commands allowed per hour."
- Queue limit: "Stops Findarr when the Arr queue is above this size; -1 disables this guard."
- Process app: "Includes this Arr app in Findarr processing."
- Monitored only: "Searches only items marked monitored in the Arr app."
- Skip future: "Skips items whose release or air date is in the future."
- Missing per cycle: "Maximum missing-item searches for this app in one Findarr cycle."
- Upgrades per cycle: "Maximum quality-upgrade searches for this app in one Findarr cycle."
- Add by Trakt URL: "Adds a Trakt list by URL when it belongs to the connected account."
- Remove list: "Stops syncing this list. It does not delete the list from Trakt."
- Sync discovered list: "Turns syncing on or off for this discovered Trakt list."
- Remove from Trakt when available: "Removes the list entry when Seer reports the item available; media files are untouched."
- Sync interval: "How often List-Syncarr polls Trakt and requests missing items in Seer."
- Bandwidth check interval: "How often the bandwidth loop checks qBittorrent and SABnzbd."
- Open metrics: "Opens the Prometheus scrape endpoint for bandwidth control gauges."
- Enable bandwidth control: "Allows SABnzbd to pause while qBittorrent has active torrents and resume when idle."
- Findarr Run all / Run Sonarr / Run Radarr: "Starts a manual Findarr run immediately, respecting configured limits."
- Reset Findarr state: "Allows previously processed items to be considered again; it does not delete media."

Verification:

- Run targeted tests:
  - `cd frontend && npm test -- src/features/settings/Settings.test.tsx`
  - `cd frontend && npm test -- src/features/findarr/Findarr.test.tsx`
  - `cd frontend && npm test -- src/features/list-syncarr/tabs/ListSettings.test.tsx`
  - `cd frontend && npm test -- src/features/list-syncarr/components/trakt-list-selector.test.tsx`
  - `cd frontend && npm test -- src/features/bandwidth-controllarr/tabs/BandwidthSettings.test.tsx`
  - `cd frontend && npm test -- src/features/findarr/tabs/Status.test.tsx`
  - `cd frontend && npm test -- src/features/bandwidth-controllarr/tabs/Status.test.tsx`
- Manually inspect the rendered settings screens at desktop and mobile widths if a browser is available.

Notes:

Applied help icons across `frontend/src/features/settings/Settings.tsx`, `frontend/src/features/findarr/tabs/Settings.tsx`, `frontend/src/features/list-syncarr/tabs/ListSettings.tsx`, `frontend/src/features/list-syncarr/components/trakt-list-selector.tsx`, `frontend/src/features/bandwidth-controllarr/tabs/BandwidthSettings.tsx`, `frontend/src/features/findarr/tabs/Status.tsx`, and `frontend/src/features/bandwidth-controllarr/tabs/Status.tsx`. Also wrapped the global Settings tab list on small screens to remove horizontal overflow discovered during Playwright verification. Deviation: `frontend/src/features/findarr/tabs/Status.test.tsx` does not exist in this repository, so Findarr status-tab coverage was added through `frontend/src/features/findarr/Findarr.test.tsx`.

## Phase 2: Test Coverage, Regression Checks, and Polish

Goal: Confirm the tooltips are discoverable, do not break existing interactions, and do not cause visual regressions.

Likely files or modules:

- The test files listed in Phase 1
- `frontend/src/App.test.tsx` only if provider assumptions need to be asserted
- `frontend/src/index.css` only if a shared utility class is required; avoid this unless necessary

Checklist:

- [x] Add tests that query help icon buttons by accessible name instead of implementation-specific selectors.
- [x] Add at least one hover or focus test per settings area to ensure tooltip content renders through the Radix portal.
- [x] Keep existing tests for form changes, autosave, mutations, and tab persistence passing without weakening assertions.
- [x] Run `cd frontend && npm run lint`.
- [x] Run `cd frontend && npm run test:types`.
- [x] Run `cd frontend && npm test -- src/features/settings/Settings.test.tsx src/features/findarr/Findarr.test.tsx src/features/list-syncarr/tabs/ListSettings.test.tsx src/features/list-syncarr/components/trakt-list-selector.test.tsx src/features/bandwidth-controllarr/tabs/BandwidthSettings.test.tsx src/features/findarr/tabs/Status.test.tsx src/features/bandwidth-controllarr/tabs/Status.test.tsx`.
- [x] Run `cd frontend && npm run build` if the targeted checks pass.
- [x] Verify `.gitignore` still excludes generated build output such as `frontend/dist/` and does not accidentally include secrets or runtime data.

Verification:

- The phase is complete when targeted tests, type checks, linting, and build pass, or when any skipped command is explicitly recorded with the reason.
- Manual verification should include hover and keyboard focus on at least one icon in each settings area: global Settings, Trakt/service settings, Findarr settings, List-Syncarr settings, and Bandwidth-Controllarr settings.

Notes:

Added tooltip tests to existing feature suites and updated isolated render helpers to wrap components in `TooltipProvider`, matching `frontend/src/main.tsx`. The exact planned command included `frontend/src/features/findarr/tabs/Status.test.tsx`, which is absent; the equivalent status behaviour is covered by `frontend/src/features/findarr/Findarr.test.tsx`. Confirmed `frontend/dist` is ignored by `frontend/.gitignore` and `plan_request_codex.md` is ignored by the root `.gitignore`.

## Verified results

Completed on 2026-06-28.

- `cd frontend && npm test -- src/shared/components/settings-help.test.tsx`: passed, 1 file and 3 tests.
- `cd frontend && npm test -- src/shared/components/ui/ui-primitives.test.tsx`: passed, 1 file and 8 tests.
- `cd frontend && npm test -- src/shared/components/settings-help.test.tsx src/features/settings/Settings.test.tsx src/features/findarr/Findarr.test.tsx src/features/list-syncarr/tabs/ListSettings.test.tsx src/features/list-syncarr/components/trakt-list-selector.test.tsx src/features/bandwidth-controllarr/tabs/BandwidthSettings.test.tsx src/features/bandwidth-controllarr/tabs/Status.test.tsx src/features/bandwidth-controllarr/BandwidthControllarr.test.tsx`: passed, 8 files and 125 tests.
- `cd frontend && npm test`: passed, 32 files and 333 tests.
- `cd frontend && npm run test:types`: passed.
- `cd frontend && npm run lint`: passed.
- `cd frontend && npm run build`: passed. Vite reported the existing-style warning that one chunk is larger than 500 kB after minification.
- Playwright smoke check against `http://127.0.0.1:5173/settings`: passed at `1280x900` and `390x844`; help buttons were present, tooltip content rendered, and horizontal overflow was false after wrapping the Settings tab list.
- Playwright smoke check against `/list-syncarr`, `/findarr`, and `/bandwidth-controllarr` Settings tabs: passed at `1280x900` and `390x844`; help buttons were present, tooltip content rendered, and horizontal overflow was false.
- `git check-ignore -v frontend/dist plan_request_codex.md`: confirmed `frontend/dist` is ignored by `frontend/.gitignore` and `plan_request_codex.md` is ignored by `.gitignore`.

## Risks

- Tooltip portals can make tests slightly more fragile if assertions assume DOM locality. Use screen-level queries against rendered text.
- Adding icon buttons near labels can unintentionally alter accessible names if nested inside labels. Keep help triggers outside the label text or give controls explicit `htmlFor`/`aria-label` values.
- Dense settings rows may wrap awkwardly on small screens. Verify mobile widths and use stable flex layouts.
- Overly long tooltip copy can become noisy. Keep each explanation short and specific to the adjacent control.
- Reusing existing descriptions and adding tooltips may create duplicate visible prose. Prefer concise persistent text plus tooltip detail where necessary, but do not remove important warnings from destructive actions.
