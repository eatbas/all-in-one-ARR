export const REMINDARR_TAB_STORAGE_KEY = "remindarr-active-tab"

export const VALID_REMINDARR_TABS = ["reminders", "settings"] as const

export type RemindarrTab = (typeof VALID_REMINDARR_TABS)[number]
