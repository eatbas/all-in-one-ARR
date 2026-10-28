/**
 * Draft state, parsing and client-side validation of the Cleanarr Settings
 * tab. Bounds mirror the backend's CLEANARR_* constants (the API enforces the
 * same rules with a 422), so invalid drafts are caught before saving.
 */
import {
  CLEANARR_EXTENSION_PATTERN,
  CLEANARR_EXTENSIONS_MAX,
  CLEANARR_IGNORE_LENGTH_MAX,
  CLEANARR_IGNORE_MAX,
  CLEANARR_INTERVAL_MAX,
  CLEANARR_INTERVAL_MIN,
  CLEANARR_MAX_STRIKES,
  CLEANARR_MIN_AGE_HOURS_MAX,
  CLEANARR_MIN_AGE_HOURS_MIN,
  CLEANARR_MIN_STRIKES,
  CLEANARR_PATH_LENGTH_MAX,
  CLEANARR_PATTERN_LENGTH_MAX,
  CLEANARR_PATTERNS_MAX,
  CLEANARR_REMOVALS_MAX,
  CLEANARR_REMOVALS_MIN,
  CLEANARR_RETENTION_DAYS_MAX,
  CLEANARR_RETENTION_DAYS_MIN,
  type CleanarrSettings,
  type CleanarrSettingsUpdate,
} from "@/shared/lib/api"

export type PatternMode = "include" | "exclude"

/** Editable values; numbers and lists stay strings until validated. */
export interface CleanarrDrafts {
  enabled: boolean
  dry_run: boolean
  interval_minutes: string
  max_strikes: string
  max_removals_per_run: string
  queue_enabled: boolean
  pattern_mode: PatternMode
  patterns: string
  malware_enabled: boolean
  extensions: string
  orphans_enabled: boolean
  min_age_hours: string
  quarantine_retention_days: string
  completed_root: string
  quarantine_dir: string
  sonarr_enabled: boolean
  radarr_enabled: boolean
  ignore_download_ids: string
  ignore_categories: string
  ignore_title_contains: string
}

export type NumericDraftKey =
  | "interval_minutes"
  | "max_strikes"
  | "max_removals_per_run"
  | "min_age_hours"
  | "quarantine_retention_days"

export type TextDraftKey =
  | NumericDraftKey
  | "patterns"
  | "extensions"
  | "completed_root"
  | "quarantine_dir"
  | "ignore_download_ids"
  | "ignore_categories"
  | "ignore_title_contains"

/** Inclusive bounds of each numeric field. */
export const NUMERIC_BOUNDS: Record<NumericDraftKey, [number, number]> = {
  interval_minutes: [CLEANARR_INTERVAL_MIN, CLEANARR_INTERVAL_MAX],
  max_strikes: [CLEANARR_MIN_STRIKES, CLEANARR_MAX_STRIKES],
  max_removals_per_run: [CLEANARR_REMOVALS_MIN, CLEANARR_REMOVALS_MAX],
  min_age_hours: [CLEANARR_MIN_AGE_HOURS_MIN, CLEANARR_MIN_AGE_HOURS_MAX],
  quarantine_retention_days: [
    CLEANARR_RETENTION_DAYS_MIN,
    CLEANARR_RETENTION_DAYS_MAX,
  ],
}

/** Draft values for a settings snapshot. */
export function toDrafts(settings: CleanarrSettings): CleanarrDrafts {
  return {
    enabled: settings.enabled,
    dry_run: settings.dry_run,
    interval_minutes: String(settings.interval_minutes),
    max_strikes: String(settings.max_strikes),
    max_removals_per_run: String(settings.max_removals_per_run),
    queue_enabled: settings.queue.enabled,
    pattern_mode: settings.queue.pattern_mode,
    patterns: settings.queue.patterns.join("\n"),
    malware_enabled: settings.malware.enabled,
    extensions: settings.malware.extensions.join(" "),
    orphans_enabled: settings.orphans.enabled,
    min_age_hours: String(settings.orphans.min_age_hours),
    quarantine_retention_days: String(
      settings.orphans.quarantine_retention_days,
    ),
    completed_root: settings.paths.completed_root,
    quarantine_dir: settings.paths.quarantine_dir,
    sonarr_enabled: settings.apps.sonarr.enabled,
    radarr_enabled: settings.apps.radarr.enabled,
    ignore_download_ids: settings.ignore.download_ids.join("\n"),
    ignore_categories: settings.ignore.categories.join("\n"),
    ignore_title_contains: settings.ignore.title_contains.join("\n"),
  }
}

/** Non-empty, trimmed lines of a one-per-line textarea. */
export function splitLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
}

/** Lower-case `.ext` entries separated by spaces, commas or new lines. */
export function parseExtensions(text: string): string[] {
  const entries = text
    .split(/[\s,]+/)
    .map((entry) => entry.trim().toLowerCase())
    .filter(Boolean)
    .map((entry) => (entry.startsWith(".") ? entry : `.${entry}`))
  return [...new Set(entries)]
}

/** A whole number within the bounds, or `null`. */
export function parseWholeNumber(
  text: string,
  [min, max]: [number, number],
): number | null {
  if (!/^\d+$/.test(text.trim())) return null
  const value = Number(text)
  return value >= min && value <= max ? value : null
}

/** An absolute path without trailing slashes (`/` stays `/`), or `null`. */
export function normalisePath(text: string): string | null {
  const trimmed = text.trim()
  if (!trimmed.startsWith("/")) return null
  return trimmed.replace(/\/+$/, "") || "/"
}

const PATH_TOO_LONG = `Use a path of at most ${CLEANARR_PATH_LENGTH_MAX} characters.`

function strictlyUnder(path: string, root: string): boolean {
  const prefix = root.endsWith("/") ? root : `${root}/`
  return path !== root && path.startsWith(prefix)
}

function boundedList(
  entries: string[],
  maxItems: number,
  maxLength: number,
): boolean {
  return (
    entries.length <= maxItems &&
    entries.every((entry) => entry.length <= maxLength)
  )
}

/** Inline error for each invalid field, keyed by draft key. */
export type DraftErrors = Partial<Record<TextDraftKey, string>>

/** The full settings payload of a draft, plus any validation errors. */
export interface DraftResult {
  update: CleanarrSettingsUpdate | null
  errors: DraftErrors
}

function numberErrors(drafts: CleanarrDrafts): {
  values: Partial<Record<NumericDraftKey, number>>
  errors: DraftErrors
} {
  const values: Partial<Record<NumericDraftKey, number>> = {}
  const errors: DraftErrors = {}
  for (const key of Object.keys(NUMERIC_BOUNDS) as NumericDraftKey[]) {
    const bounds = NUMERIC_BOUNDS[key]
    const value = parseWholeNumber(drafts[key], bounds)
    if (value === null) {
      errors[key] = `Enter a whole number from ${bounds[0]} to ${bounds[1]}.`
    } else {
      values[key] = value
    }
  }
  return { values, errors }
}

function listErrors(drafts: CleanarrDrafts): DraftErrors {
  const errors: DraftErrors = {}
  const patterns = splitLines(drafts.patterns)
  if (
    !boundedList(patterns, CLEANARR_PATTERNS_MAX, CLEANARR_PATTERN_LENGTH_MAX)
  ) {
    errors.patterns = `Use up to ${CLEANARR_PATTERNS_MAX} patterns of at most ${CLEANARR_PATTERN_LENGTH_MAX} characters.`
  }
  const extensions = parseExtensions(drafts.extensions)
  if (
    extensions.length === 0 ||
    extensions.length > CLEANARR_EXTENSIONS_MAX ||
    !extensions.every((entry) => CLEANARR_EXTENSION_PATTERN.test(entry))
  ) {
    errors.extensions = `Use 1 to ${CLEANARR_EXTENSIONS_MAX} extensions such as .exe (letters and digits only).`
  }
  for (const key of [
    "ignore_download_ids",
    "ignore_categories",
    "ignore_title_contains",
  ] as const) {
    if (
      !boundedList(
        splitLines(drafts[key]),
        CLEANARR_IGNORE_MAX,
        CLEANARR_IGNORE_LENGTH_MAX,
      )
    ) {
      errors[key] =
        `Use up to ${CLEANARR_IGNORE_MAX} entries of at most ${CLEANARR_IGNORE_LENGTH_MAX} characters.`
    }
  }
  return errors
}

function pathErrors(drafts: CleanarrDrafts): DraftErrors {
  const errors: DraftErrors = {}
  const root = normalisePath(drafts.completed_root)
  const quarantine = normalisePath(drafts.quarantine_dir)
  if (root === null) {
    errors.completed_root =
      "Enter an absolute path, such as /downloads/complete."
  } else if (root.length > CLEANARR_PATH_LENGTH_MAX) {
    errors.completed_root = PATH_TOO_LONG
  }
  if (
    quarantine === null ||
    (root !== null && !strictlyUnder(quarantine, root))
  ) {
    errors.quarantine_dir =
      "Enter an absolute path inside the completed folder."
  } else if (quarantine.length > CLEANARR_PATH_LENGTH_MAX) {
    errors.quarantine_dir = PATH_TOO_LONG
  }
  return errors
}

/** Validate a draft; `update` is `null` while any field is invalid. */
export function validateDrafts(drafts: CleanarrDrafts): DraftResult {
  const { values, errors: numeric } = numberErrors(drafts)
  const errors = { ...numeric, ...listErrors(drafts), ...pathErrors(drafts) }
  if (Object.keys(errors).length > 0) return { update: null, errors }
  return {
    errors,
    update: {
      enabled: drafts.enabled,
      dry_run: drafts.dry_run,
      interval_minutes: values.interval_minutes,
      max_strikes: values.max_strikes,
      max_removals_per_run: values.max_removals_per_run,
      queue: {
        enabled: drafts.queue_enabled,
        pattern_mode: drafts.pattern_mode,
        patterns: splitLines(drafts.patterns),
      },
      malware: {
        enabled: drafts.malware_enabled,
        extensions: parseExtensions(drafts.extensions),
      },
      orphans: {
        enabled: drafts.orphans_enabled,
        min_age_hours: values.min_age_hours,
        quarantine_retention_days: values.quarantine_retention_days,
      },
      paths: {
        completed_root: normalisePath(drafts.completed_root) as string,
        quarantine_dir: normalisePath(drafts.quarantine_dir) as string,
      },
      apps: {
        sonarr: { enabled: drafts.sonarr_enabled },
        radarr: { enabled: drafts.radarr_enabled },
      },
      ignore: {
        download_ids: splitLines(drafts.ignore_download_ids),
        categories: splitLines(drafts.ignore_categories),
        title_contains: splitLines(drafts.ignore_title_contains),
      },
    },
  }
}

/** Whether a validated draft differs from the saved settings. */
export function isDirty(
  update: CleanarrSettingsUpdate,
  settings: CleanarrSettings,
): boolean {
  const saved = validateDrafts(toDrafts(settings)).update
  return JSON.stringify(update) !== JSON.stringify(saved)
}
