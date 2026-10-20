import {
  CheckboxGroup,
  type CheckboxOption,
} from "@/features/languagarr/components/checkbox-group"
import {
  LANGUAGARR_MAX_LANGUAGES,
  type LanguagarrAudioLanguage,
} from "@/shared/lib/api"
import { useLanguagarrLanguages } from "@/shared/lib/queries"

interface LanguageChecklistProps {
  /** Canonical target language codes (the draft, not the saved settings). */
  selected: string[]
  onChange: (next: string[]) => void
  disabled: boolean
}

/**
 * The catalogue in its own order, then any selected code it does not list (only
 * possible while the catalogue is loading or failed), shown by its code so the
 * saved choice stays visible and editable.
 */
function languageOptions(
  catalogue: LanguagarrAudioLanguage[],
  selected: string[],
): CheckboxOption[] {
  const known = new Set(catalogue.map((language) => language.code))
  return [
    ...catalogue.map((language) => ({
      value: language.code,
      label: language.name,
    })),
    ...selected
      .filter((code) => !known.has(code))
      .map((code) => ({ value: code, label: code.toUpperCase() })),
  ]
}

/** Status line under the checklist while the catalogue loads or fails. */
function languagesNotice(
  isLoading: boolean,
  error: Error | null,
): string | null {
  if (isLoading) return "Loading languages…"
  if (error) return `Could not load the language list: ${error.message}`
  return null
}

/**
 * Checklist of the audio languages a replacement must carry. A file passes when
 * it has a track in any checked language; at most
 * {@link LANGUAGARR_MAX_LANGUAGES} can be checked, matching the API limit.
 */
export function LanguageChecklist({
  selected,
  onChange,
  disabled,
}: LanguageChecklistProps) {
  const { data, isLoading, error } = useLanguagarrLanguages()

  return (
    <CheckboxGroup
      id="languagarr-language"
      label="Target audio languages"
      options={languageOptions(data ?? [], selected)}
      selected={selected}
      onChange={onChange}
      disabled={disabled}
      max={LANGUAGARR_MAX_LANGUAGES}
      notice={languagesNotice(isLoading, error)}
      help="A file passes when it has an audio track in any checked language; files with none of them are listed for replacement. Sonarr still picks the release by its own custom-format scores, so make sure the profile favours these languages."
    />
  )
}
