import {
  CheckboxGroup,
  type CheckboxOption,
} from "@/shared/components/checkbox-group"
import { REMINDARR_MAX_TAGS, type RemindarrTag } from "@/shared/lib/api"
import { useRemindarrTags } from "@/shared/lib/queries"
import { tagLabel } from "@/features/remindarr/labels"

interface TagChecklistProps {
  /** Selected tag ids (the draft, not the saved settings). */
  selected: number[]
  onChange: (next: number[]) => void
  disabled: boolean
}

/**
 * Sonarr's tags first (in Sonarr's label order), then any selected id Sonarr
 * did not report, labelled "tag <id>". Keeping a stale tag visible lets the
 * user uncheck it. It is flagged "not in Sonarr" only once Sonarr has answered
 * (`sonarrTags` defined), never while the tags load or fail to load. Ids are
 * strings inside {@link CheckboxGroup}.
 */
function tagOptions(
  sonarrTags: RemindarrTag[] | undefined,
  selected: number[],
): CheckboxOption[] {
  const known = new Set((sonarrTags ?? []).map((tag) => tag.id))
  const warning = sonarrTags ? "not in Sonarr" : undefined
  return [
    ...(sonarrTags ?? []).map((tag) => ({
      value: String(tag.id),
      label: tag.label,
    })),
    ...selected
      .filter((tagId) => !known.has(tagId))
      .map((tagId) => ({
        value: String(tagId),
        label: tagLabel(tagId, undefined),
        warning,
      })),
  ]
}

/** Status line under the checklist: loading, load failure, or no tags. */
function tagsNotice(
  isLoading: boolean,
  error: Error | null,
  sonarrCount: number,
): string | null {
  if (isLoading) return "Loading Sonarr tags…"
  if (error) return `Could not load Sonarr tags: ${error.message}`
  if (sonarrCount === 0) return "Sonarr reported no tags."
  return null
}

/**
 * Checklist of Sonarr tags whose series Remindarr tracks. Options come live
 * from Sonarr; at most {@link REMINDARR_MAX_TAGS} can be checked, matching the
 * API limit.
 */
export function TagChecklist({
  selected,
  onChange,
  disabled,
}: TagChecklistProps) {
  const { data, isLoading, error } = useRemindarrTags()

  return (
    <CheckboxGroup
      id="remindarr-tag"
      label="Sonarr tags to track"
      options={tagOptions(data, selected)}
      selected={selected.map(String)}
      onChange={(next) => onChange(next.map(Number))}
      disabled={disabled}
      max={REMINDARR_MAX_TAGS}
      notice={tagsNotice(isLoading, error, data?.length ?? 0)}
      help="Series carrying any checked tag are tracked. A tag marked “not in Sonarr” matches no series until you uncheck it."
    />
  )
}
