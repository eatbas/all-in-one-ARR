export const CLEANARR_TAB_STORAGE_KEY = "aio-arr.cleanarr.active-tab"

export const VALID_CLEANARR_TABS = [
  "status",
  "queue",
  "history",
  "settings",
] as const

export type CleanarrTab = (typeof VALID_CLEANARR_TABS)[number]
