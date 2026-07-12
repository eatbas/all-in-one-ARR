import {
  DEFAULT_LIST_SYNCARR_DENSITY,
  type PosterDensity,
} from "@/shared/components/poster-grid/poster-grid-density"

/** localStorage key for the last active List-Syncarr tab. */
export const LIST_SYNCARR_TAB_STORAGE_KEY = "aio-arr-list-syncarr-active-tab"

/** localStorage key remembering the List-Syncarr posters-per-row density. */
export const LIST_SYNCARR_PER_ROW_STORAGE_KEY = "aio-arr.list-syncarr.per-row"

/** ListSyncarr's default posters-per-row density when no valid preference is stored. */
export const DEFAULT_LIST_SYNCARR_PER_ROW: PosterDensity =
  DEFAULT_LIST_SYNCARR_DENSITY

/** Every tab value that can be persisted in the List-Syncarr active-tab store. */
export const VALID_LIST_SYNCARR_TABS: readonly string[] = ["lists", "settings"]
