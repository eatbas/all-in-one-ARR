import type { ServiceName } from "@/shared/lib/api"

type ServiceField = "url" | "apiKey"

export interface ServiceTab {
  name: ServiceName
  label: string
  fields: readonly ServiceField[]
}

/**
 * The managed integration services, in display order. This is the single source
 * of truth used by both the Settings tabs and the Lists status dashboard.
 */
export const SERVICE_TABS: readonly ServiceTab[] = [
  { name: "jellyseerr", label: "Jellyseerr", fields: ["url", "apiKey"] },
  { name: "sonarr", label: "Sonarr", fields: ["url", "apiKey"] },
  { name: "radarr", label: "Radarr", fields: ["url", "apiKey"] },
  { name: "tmdb", label: "TMDB", fields: ["apiKey"] },
  { name: "omdb", label: "OMDb", fields: ["apiKey"] },
  { name: "sabnzbd", label: "SABnzbd", fields: ["url", "apiKey"] },
  { name: "qbittorrent", label: "qBittorrent", fields: ["url", "apiKey"] },
]

/** Every tab value that can be persisted in the settings active-tab store. */
export const VALID_TAB_VALUES: readonly string[] = [
  "general",
  "trakt",
  ...SERVICE_TABS.map((tab) => tab.name),
]
