export const FINDARR_TAB_STORAGE_KEY = "aio-arr.findarr.active-tab"

export const VALID_FINDARR_TABS = ["status", "settings", "history"] as const

export type FindarrTab = (typeof VALID_FINDARR_TABS)[number]
