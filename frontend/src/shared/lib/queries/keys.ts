import type { DeletarrLibraryType, TrendingQuery } from "@/shared/lib/api"

/** Stable query keys so mutations can target invalidations precisely. */
export const queryKeys = {
  status: ["status"] as const,
  activity: ["activity"] as const,
  lists: ["lists"] as const,
  listItems: (slug: string) => ["items", "by-list", slug] as const,
  traktSettings: ["trakt", "settings"] as const,
  traktAuthStatus: ["trakt", "auth-status"] as const,
  traktLists: ["trakt", "lists"] as const,
  services: ["services"] as const,
  serviceStatuses: ["service-statuses"] as const,
  generalSettings: ["general", "settings"] as const,
  database: ["database", "stats"] as const,
  bandwidthStatus: ["bandwidth", "status"] as const,
  deletarrStatus: ["deletarr", "status"] as const,
  deletarrSettings: ["deletarr", "settings"] as const,
  deletarrResults: (type: DeletarrLibraryType) =>
    ["deletarr", "results", type] as const,
  findarrStatus: ["findarr", "status"] as const,
  findarrSettings: ["findarr", "settings"] as const,
  findarrHistory: ["findarr", "history"] as const,
  trending: (query: TrendingQuery) =>
    ["trending", query.source, query.media, query.category] as const,
  trendingStatus: ["trending", "status"] as const,
}
