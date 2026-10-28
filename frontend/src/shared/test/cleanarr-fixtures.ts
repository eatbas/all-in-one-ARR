/** Shared Cleanarr test data for the API, query and page suites. */
import type {
  CleanarrHistoryEntry,
  CleanarrQueue,
  CleanarrQueueItem,
  CleanarrSettings,
  CleanarrStatus,
} from "@/shared/lib/api"

export const CLEANARR_SETTINGS: CleanarrSettings = {
  enabled: true,
  dry_run: true,
  interval_minutes: 10,
  max_strikes: 3,
  max_removals_per_run: 10,
  queue: {
    enabled: true,
    pattern_mode: "exclude",
    patterns: ["matched to series by ID", "matched to movie by ID"],
  },
  malware: { enabled: false, extensions: [".exe", ".scr"] },
  orphans: { enabled: false, min_age_hours: 24, quarantine_retention_days: 14 },
  paths: {
    completed_root: "/downloads/complete",
    quarantine_dir: "/downloads/complete/_cleanarr_quarantine",
  },
  apps: { sonarr: { enabled: true }, radarr: { enabled: true } },
  ignore: {
    download_ids: ["SABnzbd_nzo_x"],
    categories: [],
    title_contains: [],
  },
}

export const CLEANARR_STATUS: CleanarrStatus = {
  settings: CLEANARR_SETTINGS,
  enabled: true,
  dry_run: true,
  running: false,
  last_run: {
    at: "2026-10-27T14:20:00Z",
    status: "completed",
    detail: "Dry run: 1 would remove",
  },
  connections: [
    { app: "sabnzbd", ok: true, detail: "Connected to SABnzbd" },
    { app: "radarr", ok: false, detail: "connection refused" },
    { app: "sonarr", ok: true, detail: "Connected to Sonarr 4.0.1" },
  ],
  health: [
    {
      source: "sabnzbd",
      code: "unwanted_action_not_abort",
      detail: "SABnzbd does not abort jobs containing unwanted extensions.",
      level: "warning",
    },
    {
      source: "radarr",
      code: "download_handling_unknown",
      detail: "Could not read Radarr's download handling settings.",
      level: "info",
    },
  ],
  strikes: { sonarr: 3, radarr: 1, failed_import: 3, failed_download: 1 },
}

export function cleanarrQueueItem(
  overrides: Partial<CleanarrQueueItem> = {},
): CleanarrQueueItem {
  return {
    app: "sonarr",
    queue_id: 1,
    download_id: "SABnzbd_nzo_1",
    title: "The.Last.of.Us.S02E03.1080p",
    reason: "failed_import",
    message: "No files found are eligible for import",
    strikes: 3,
    max_strikes: 3,
    would_remove: true,
    ignored: false,
    excluded: false,
    ...overrides,
  }
}

export const CLEANARR_QUEUE: CleanarrQueue = {
  items: [cleanarrQueueItem()],
  errors: {},
  held: {},
  max_strikes: 3,
  dry_run: true,
}

export const CLEANARR_HISTORY: CleanarrHistoryEntry[] = [
  {
    id: 2,
    ts: "2026-10-27T14:20:00Z",
    app: "sonarr",
    action: "would_remove",
    download_id: "SABnzbd_nzo_1",
    title: "The.Last.of.Us.S02E03.1080p",
    detail: "failed_import",
    dry_run: true,
  },
  {
    id: 1,
    ts: "2026-10-25T14:20:00Z",
    app: "sabnzbd",
    action: "purged",
    download_id: null,
    title: null,
    detail: "",
    dry_run: false,
  },
]
