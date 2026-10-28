import { describe, expect, it } from "vitest"

import {
  actionMeta,
  historyDetail,
  sourceLabel,
} from "@/features/cleanarr/labels"

describe("Cleanarr labels", () => {
  it.each([
    ["sonarr", "Sonarr"],
    ["sabnzbd", "SABnzbd"],
    ["system", "Cleanarr"],
    ["lidarr", "lidarr"],
  ])("labels the source %s as %s", (source, label) => {
    expect(sourceLabel(source)).toBe(label)
  })

  it.each([
    ["would_remove", "Would remove", "amber"],
    ["removed", "Removed", "emerald"],
    ["would_delete_malware", "Would delete file", "red"],
    ["quarantined", "Quarantined", "sky"],
    ["purged", "Purged", "neutral"],
    ["something_new", "something_new", "neutral"],
  ])("labels the action %s", (action, label, tone) => {
    expect(actionMeta(action)).toEqual({ label, tone })
  })

  it.each([
    [
      "removed",
      "failed_download",
      "Blocklisted and searching again · failed download",
    ],
    ["removed", "custom", "Blocklisted and searching again · custom"],
    ["would_remove", "failed_import", "failed import"],
    ["already_gone", "failed_import", "Item had already left the queue"],
    ["remove_failed", "HTTP 500", "HTTP 500; strike kept"],
    ["malware_deleted", "setup.exe", "setup.exe"],
    ["purged", "", "—"],
  ])("describes %s / %s", (action, detail, text) => {
    expect(historyDetail(action, detail)).toBe(text)
  })
})
