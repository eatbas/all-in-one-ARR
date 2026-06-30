export const DELETARR_TAB_STORAGE_KEY = "deletarr-active-tab"

export const VALID_DELETARR_TABS = ["movies", "tv", "settings"] as const

export type DeletarrTab = (typeof VALID_DELETARR_TABS)[number]
