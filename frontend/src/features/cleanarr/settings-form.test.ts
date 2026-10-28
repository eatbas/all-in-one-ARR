import { describe, expect, it } from "vitest"

import {
  isDirty,
  normalisePath,
  parseExtensions,
  parseWholeNumber,
  splitLines,
  toDrafts,
  validateDrafts,
  type CleanarrDrafts,
} from "@/features/cleanarr/settings-form"
import { CLEANARR_SETTINGS } from "@/shared/test/cleanarr-fixtures"

function drafts(overrides: Partial<CleanarrDrafts> = {}): CleanarrDrafts {
  return { ...toDrafts(CLEANARR_SETTINGS), ...overrides }
}

describe("Cleanarr settings form helpers", () => {
  it("splits one-per-line text", () => {
    expect(splitLines(" a \n\n b\n  ")).toEqual(["a", "b"])
  })

  it("parses extensions separated by spaces, commas or new lines", () => {
    expect(parseExtensions("EXE, .scr\n.lnk  .exe")).toEqual([
      ".exe",
      ".scr",
      ".lnk",
    ])
    expect(parseExtensions("   ")).toEqual([])
  })

  it.each([
    ["10", [5, 1440], 10],
    [" 5 ", [5, 1440], 5],
    ["4", [5, 1440], null],
    ["1441", [5, 1440], null],
    ["1.5", [1, 3], null],
    ["", [1, 3], null],
    ["-1", [1, 3], null],
  ] as const)("parses %j within %j", (text, bounds, expected) => {
    expect(parseWholeNumber(text, [...bounds])).toBe(expected)
  })

  it.each([
    ["/downloads/complete/", "/downloads/complete"],
    [" /data ", "/data"],
    ["/", "/"],
    ["relative/path", null],
    ["", null],
  ])("normalises the path %j", (text, expected) => {
    expect(normalisePath(text)).toBe(expected)
  })
})

describe("validateDrafts", () => {
  it("builds the full update from valid drafts", () => {
    const { update, errors } = validateDrafts(
      drafts({
        max_strikes: "5",
        patterns: "one\n\n two ",
        extensions: "EXE scr",
        completed_root: "/data/done/",
        quarantine_dir: "/data/done/q",
        ignore_categories: "anime\n",
      }),
    )
    expect(errors).toEqual({})
    expect(update).toMatchObject({
      max_strikes: 5,
      queue: { patterns: ["one", "two"], pattern_mode: "exclude" },
      malware: { extensions: [".exe", ".scr"] },
      paths: { completed_root: "/data/done", quarantine_dir: "/data/done/q" },
      apps: { sonarr: { enabled: true }, radarr: { enabled: true } },
      ignore: {
        download_ids: ["SABnzbd_nzo_x"],
        categories: ["anime"],
        title_contains: [],
      },
    })
  })

  it("reports every invalid field and builds no update", () => {
    const { update, errors } = validateDrafts(
      drafts({
        interval_minutes: "4",
        max_strikes: "2",
        max_removals_per_run: "51",
        min_age_hours: "0",
        quarantine_retention_days: "x",
        patterns: Array.from({ length: 51 }, (_, i) => `p${i}`).join("\n"),
        extensions: ".exe .bad-ext",
        completed_root: "relative",
        quarantine_dir: "/elsewhere",
        ignore_download_ids: "x".repeat(201),
        ignore_categories: Array.from({ length: 501 }, (_, i) => `c${i}`).join(
          "\n",
        ),
        ignore_title_contains: "fine",
      }),
    )
    expect(update).toBeNull()
    expect(errors).toEqual({
      interval_minutes: "Enter a whole number from 5 to 1440.",
      max_strikes: "Enter a whole number from 3 to 20.",
      max_removals_per_run: "Enter a whole number from 1 to 50.",
      min_age_hours: "Enter a whole number from 1 to 720.",
      quarantine_retention_days: "Enter a whole number from 1 to 365.",
      patterns: "Use up to 50 patterns of at most 200 characters.",
      extensions:
        "Use 1 to 100 extensions such as .exe (letters and digits only).",
      // The quarantine folder is only checked against a valid completed folder.
      completed_root: "Enter an absolute path, such as /downloads/complete.",
      ignore_download_ids: "Use up to 500 entries of at most 200 characters.",
      ignore_categories: "Use up to 500 entries of at most 200 characters.",
    })
  })

  it.each([
    ["no extensions", { extensions: "" }],
    [
      "too many extensions",
      {
        extensions: Array.from({ length: 101 }, (_, i) => `.e${i}`).join(" "),
      },
    ],
    ["a relative quarantine", { quarantine_dir: "q" }],
    [
      "the quarantine equal to the root",
      { quarantine_dir: "/downloads/complete" },
    ],
  ])("rejects %s", (_name, overrides) => {
    expect(validateDrafts(drafts(overrides)).update).toBeNull()
  })

  it("mirrors the backend's 1,024-character path bound", () => {
    const root = `/${"a".repeat(999)}`
    const quarantine = `${root}/${"q".repeat(23)}`
    expect(quarantine).toHaveLength(1024)
    const atLimit = validateDrafts(
      drafts({ completed_root: root, quarantine_dir: quarantine }),
    )
    expect(atLimit.errors).toEqual({})

    const longRoot = `/${"a".repeat(1024)}`
    const tooLong = validateDrafts(
      drafts({ completed_root: longRoot, quarantine_dir: `${longRoot}/q` }),
    )
    expect(tooLong.update).toBeNull()
    expect(tooLong.errors).toEqual({
      completed_root: "Use a path of at most 1024 characters.",
      quarantine_dir: "Use a path of at most 1024 characters.",
    })

    const longQuarantine = validateDrafts(
      drafts({ quarantine_dir: `/downloads/complete/${"q".repeat(1010)}` }),
    )
    expect(longQuarantine.errors).toEqual({
      quarantine_dir: "Use a path of at most 1024 characters.",
    })
  })

  it("accepts a quarantine under the filesystem root", () => {
    const result = validateDrafts(
      drafts({ completed_root: "/", quarantine_dir: "/q" }),
    )
    expect(result.update?.paths).toEqual({
      completed_root: "/",
      quarantine_dir: "/q",
    })
  })
})

describe("isDirty", () => {
  it("is false for untouched drafts and true after a change", () => {
    const clean = validateDrafts(drafts()).update
    expect(clean && isDirty(clean, CLEANARR_SETTINGS)).toBe(false)
    const changed = validateDrafts(drafts({ dry_run: false })).update
    expect(changed && isDirty(changed, CLEANARR_SETTINGS)).toBe(true)
  })

  it("treats saved settings that no longer validate as dirty", () => {
    const update = validateDrafts(drafts()).update
    const broken = { ...CLEANARR_SETTINGS, max_strikes: 99 }
    expect(update && isDirty(update, broken)).toBe(true)
  })
})
