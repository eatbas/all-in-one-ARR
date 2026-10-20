import {
  CheckboxGroup,
  type CheckboxOption,
} from "@/features/languagarr/components/checkbox-group"
import { LANGUAGARR_MAX_PROFILES } from "@/shared/lib/api"
import { useLanguagarrProfiles } from "@/shared/lib/queries"

interface ProfileChecklistProps {
  /** Profile names currently in scope (the draft, not the saved settings). */
  selected: string[]
  onChange: (next: string[]) => void
  disabled: boolean
}

/**
 * Sonarr's profiles first (in Sonarr's name order), then any selected name
 * Sonarr does not report. Keeping a stale name visible lets the user uncheck
 * it; otherwise the next scan would fail on a profile they cannot see.
 */
function profileOptions(
  sonarrNames: string[],
  selected: string[],
): CheckboxOption[] {
  const known = new Set(sonarrNames)
  return [
    ...sonarrNames.map((name) => ({ value: name, label: name })),
    ...selected
      .filter((name) => !known.has(name))
      .map((name) => ({ value: name, label: name, warning: "not in Sonarr" })),
  ]
}

/** Status line under the checklist: loading, load failure, or an empty Sonarr. */
function profilesNotice(
  isLoading: boolean,
  error: Error | null,
  sonarrCount: number,
): string | null {
  if (isLoading) return "Loading Sonarr quality profiles…"
  if (error) return `Could not load Sonarr quality profiles: ${error.message}`
  if (sonarrCount === 0) return "Sonarr reported no quality profiles."
  return null
}

/**
 * Checklist of Sonarr quality profiles for Languagarr's scan scope. Options come
 * live from Sonarr, so a scope can only be built from profiles that exist; at
 * most {@link LANGUAGARR_MAX_PROFILES} can be checked, matching the API limit.
 */
export function ProfileChecklist({
  selected,
  onChange,
  disabled,
}: ProfileChecklistProps) {
  const { data, isLoading, error } = useLanguagarrProfiles()
  const sonarrNames = (data ?? []).map((profile) => profile.name)

  return (
    <CheckboxGroup
      id="languagarr-profile"
      label="Sonarr quality profiles in scope"
      options={profileOptions(sonarrNames, selected)}
      selected={selected}
      onChange={onChange}
      disabled={disabled}
      max={LANGUAGARR_MAX_PROFILES}
      notice={profilesNotice(isLoading, error, sonarrNames.length)}
      help="Only series using a checked profile are scanned. Pick at least one; a profile marked “not in Sonarr” stops the scan until you uncheck it."
    />
  )
}
