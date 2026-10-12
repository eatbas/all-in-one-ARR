export const LANGUAGARR_TAB_STORAGE_KEY = "languagarr-active-tab"

export const VALID_LANGUAGARR_TABS = ["review", "queue", "settings"] as const

export type LanguagarrTab = (typeof VALID_LANGUAGARR_TABS)[number]
