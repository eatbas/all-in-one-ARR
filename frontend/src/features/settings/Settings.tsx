import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"

import { Button } from "@/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import { Input } from "@/shared/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs"
import {
  ConnectionBadge,
  type ConnectionState,
} from "@/shared/components/connection-badge"
import { SettingsHelp } from "@/shared/components/settings-help"
import {
  ActionWithHelp,
  ClearAction,
  Field,
} from "@/features/settings/components/settings-form"
import { useAutosave } from "@/features/settings/hooks/use-autosave"
import { useTheme } from "@/shared/components/theme-context"
import { cn } from "@/shared/lib/utils"
import {
  SERVICE_TABS,
  VALID_TAB_VALUES,
  type ServiceTab,
} from "@/shared/lib/services"
import { SETTINGS_TAB_STORAGE_KEY } from "@/features/settings/settings-tab"
import { THEME_OPTIONS } from "@/shared/lib/theme-options"
import { formatBytes } from "@/shared/lib/format"
import {
  queryKeys,
  useClearActivity,
  useClearItems,
  useClearPosters,
  useDatabaseStats,
  useGeneralSettings,
  useServiceSettings,
  useServiceStatuses,
  useStartTraktAuth,
  useTestService,
  useTestTrakt,
  useTraktAuthStatus,
  useTraktSettings,
  useUpdateAnimeIdsRefresh,
  useUpdateOmdbBudget,
  useUpdateRatingTtl,
  useUpdateServiceSettings,
  useUpdateStatusInterval,
  useUpdateTraktSettings,
  useUpdateTrendingInterval,
} from "@/shared/lib/queries"
import { isLikelyInternalUrl, normaliseServiceUrl } from "@/shared/lib/api"
import type {
  UpdateServicePayload,
  UpdateTraktSettings,
} from "@/shared/lib/api"
import { useQueryClient } from "@tanstack/react-query"

/** Edit the Trakt credentials, authorise the app, and test the connection. */
function CredentialsCard() {
  const { data: settings, isLoading } = useTraktSettings()
  const { data: auth } = useTraktAuthStatus()
  const { mutate: updateTraktSettings, isPending: isUpdatingTraktSettings } =
    useUpdateTraktSettings()
  const startAuth = useStartTraktAuth()
  const test = useTestTrakt()
  const queryClient = useQueryClient()
  const [clientIdEdit, setClientIdEdit] = useState<string | null>(null)
  const [clientSecret, setClientSecret] = useState("")
  const [traktDraftRevision, setTraktDraftRevision] = useState(0)

  const savedClientId = settings?.client_id ?? ""
  const clientId = clientIdEdit ?? savedClientId

  const traktBody = useMemo<UpdateTraktSettings | null>(() => {
    const body: UpdateTraktSettings = {}
    if (clientId.trim() !== savedClientId.trim()) {
      body.client_id = clientId
    }
    if (clientSecret) {
      body.client_secret = clientSecret
    }
    return Object.keys(body).length > 0 ? body : null
  }, [clientId, clientSecret, savedClientId])

  const clearTraktEdit = useCallback(() => {
    setClientSecret("")
    setClientIdEdit(null)
  }, [])

  const editClientId = useCallback((value: string) => {
    setClientIdEdit(value)
    setTraktDraftRevision((revision) => revision + 1)
  }, [])

  const editClientSecret = useCallback((value: string) => {
    setClientSecret(value)
    setTraktDraftRevision((revision) => revision + 1)
  }, [])

  useAutosave({
    body: traktBody,
    draftRevision: traktDraftRevision,
    mutate: updateTraktSettings,
    isPending: isUpdatingTraktSettings,
    onSuccess: clearTraktEdit,
  })

  const connected = settings?.connected ?? false
  const pending = auth && auth.state === "pending" ? auth : undefined
  const failedMessage =
    auth && auth.state === "failed" ? auth.message : undefined

  // Once device auth reports connected, refresh Trakt settings and the
  // discovered lists so the list selector populates immediately. The whole
  // `auth` object is watched (rather than just `auth.connected`) so a transition
  // from pending to connected always fires the effect even if the boolean value
  // were already true from a stale cache.
  const wasConnectedRef = useRef(false)
  useEffect(() => {
    if (auth?.connected && !wasConnectedRef.current) {
      wasConnectedRef.current = true
      void queryClient.invalidateQueries({ queryKey: queryKeys.traktSettings })
      void queryClient.invalidateQueries({ queryKey: queryKeys.traktLists })
    } else if (!auth?.connected) {
      wasConnectedRef.current = false
    }
  }, [auth, queryClient])

  const clientIdHint = isUpdatingTraktSettings
    ? "Saving…"
    : settings?.client_id_set
      ? "Saved"
      : "Not set"
  const clientSecretHint = clientSecret
    ? "Unsaved"
    : settings?.client_secret_set
      ? "Saved"
      : "Not set"

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
        <div>
          <CardTitle>Trakt credentials</CardTitle>
          <CardDescription>
            From your application at trakt.tv/oauth/applications. The secret is
            stored server-side and never shown again.
          </CardDescription>
        </div>
        <ConnectionBadge
          state={connected ? "connected" : "not-set"}
          labels={{ "not-set": "Not connected" }}
        />
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <>
            <Field
              label="Client ID"
              hint={clientIdHint}
              helpText="The public client identifier from your Trakt application."
            >
              <Input
                value={clientId}
                onChange={(event) => editClientId(event.target.value)}
                placeholder="Trakt client id"
              />
            </Field>
            <Field
              label="Client secret"
              hint={clientSecretHint}
              helpText="The private Trakt application secret. It is saved server-side and not shown again."
            >
              <Input
                type="password"
                value={clientSecret}
                onChange={(event) => editClientSecret(event.target.value)}
                placeholder="Leave blank to keep current"
              />
            </Field>
            <div className="flex flex-wrap gap-3">
              <ActionWithHelp
                label={connected ? "Re-connect Trakt" : "Connect Trakt"}
                helpText="Starts Trakt device authorisation so this app can read and update your selected lists."
              >
                <Button
                  onClick={() => startAuth.mutate()}
                  disabled={startAuth.isPending}
                >
                  {connected ? "Re-connect Trakt" : "Connect Trakt"}
                </Button>
              </ActionWithHelp>
              <ActionWithHelp
                label="Test connection"
                helpText="Checks the saved credentials or token without changing settings."
              >
                <Button
                  variant="outline"
                  onClick={() => test.mutate()}
                  disabled={test.isPending}
                >
                  Test connection
                </Button>
              </ActionWithHelp>
            </div>
            {pending?.user_code ? (
              <div className="rounded-md border bg-muted/40 p-4 text-sm">
                <p>
                  Go to{" "}
                  <a
                    className="font-medium underline"
                    href={
                      pending.verification_url ?? "https://trakt.tv/activate"
                    }
                    target="_blank"
                    rel="noreferrer"
                  >
                    {pending.verification_url ?? "trakt.tv/activate"}
                  </a>{" "}
                  and enter code{" "}
                  <span className="font-mono font-semibold">
                    {pending.user_code}
                  </span>
                </p>
                <p className="mt-1 text-muted-foreground">{pending.message}</p>
              </div>
            ) : null}
            {failedMessage ? (
              <p className="text-sm text-destructive">{failedMessage}</p>
            ) : null}
            {test.data ? (
              <p
                className={cn(
                  "text-sm",
                  test.data.ok
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-destructive",
                )}
              >
                {test.data.ok
                  ? `Connection OK${test.data.user ? ` — ${test.data.user}` : ""}`
                  : test.data.message}
              </p>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  )
}

/** Edit a service connection (URL / API key) and test it. */
/** UI metadata for the API-key slots a service tab can declare. */
const API_KEY_FIELDS = [
  {
    field: "apiKey",
    payload: "api_key",
    setFlag: "api_key_set",
    label: "API key",
  },
  {
    field: "apiKey2",
    payload: "api_key_2",
    setFlag: "api_key_2_set",
    label: "API key 2 (optional)",
  },
  {
    field: "apiKey3",
    payload: "api_key_3",
    setFlag: "api_key_3_set",
    label: "API key 3 (optional)",
  },
  {
    field: "apiKey4",
    payload: "api_key_4",
    setFlag: "api_key_4_set",
    label: "API key 4 (optional)",
  },
] as const

type ApiKeyFieldMeta = (typeof API_KEY_FIELDS)[number]

function ServiceConnectionCard({ name, label, fields }: ServiceTab) {
  const { data: services } = useServiceSettings()
  const { data: statuses } = useServiceStatuses()
  const {
    mutate: updateServiceSettings,
    isPending: isUpdatingServiceSettings,
  } = useUpdateServiceSettings()
  const test = useTestService()
  const current = services?.[name]
  const [urlEdit, setUrlEdit] = useState<string | null>(null)
  const [keyEdits, setKeyEdits] = useState<Record<string, string>>({})
  const [serviceDraftRevision, setServiceDraftRevision] = useState(0)

  // Every managed service carries an API key; only some also carry a URL, and
  // OMDb additionally declares up to three optional rotation-key slots.
  const hasUrl = fields.includes("url")
  const keyFields = API_KEY_FIELDS.filter((key) => fields.includes(key.field))
  const savedUrl = current?.url ?? ""
  const url = urlEdit ?? savedUrl

  const serviceBody = useMemo<UpdateServicePayload | null>(() => {
    const body: UpdateServicePayload = {}
    if (hasUrl && url.trim() !== savedUrl.trim()) {
      try {
        body.url = normaliseServiceUrl(url)
      } catch {
        // Invalid URLs are left as-is so the server can reject them and the UI
        // can surface the error; do not silently swallow the user's input.
        body.url = url
      }
    }
    for (const key of keyFields) {
      const draft = keyEdits[key.payload]
      if (draft) {
        body[key.payload] = draft
      }
    }
    return Object.keys(body).length > 0 ? body : null
  }, [hasUrl, url, keyEdits, keyFields, savedUrl])

  const urlLooksInternal = hasUrl && isLikelyInternalUrl(url)

  const clearServiceEdit = useCallback(() => {
    setKeyEdits({})
    setUrlEdit(null)
  }, [])

  const editUrl = useCallback((value: string) => {
    setUrlEdit(value)
    setServiceDraftRevision((revision) => revision + 1)
  }, [])

  const editKey = useCallback((payload: string, value: string) => {
    setKeyEdits((edits) => ({ ...edits, [payload]: value }))
    setServiceDraftRevision((revision) => revision + 1)
  }, [])

  const saveService = useCallback(
    (body: UpdateServicePayload, options?: { onSuccess?: () => void }) =>
      updateServiceSettings({ name, body }, options),
    [name, updateServiceSettings],
  )

  useAutosave({
    body: serviceBody,
    draftRevision: serviceDraftRevision,
    mutate: saveService,
    isPending: isUpdatingServiceSettings,
    onSuccess: clearServiceEdit,
  })

  // The badge reflects both whether the API key is set and the live status
  // snapshot from the background checker.
  const configured = current?.api_key_set ?? false
  const snapshot = statuses?.services?.[name]
  const connectionState: ConnectionState = !configured
    ? "not-set"
    : snapshot === undefined
      ? "checking"
      : snapshot.ok
        ? "connected"
        : "offline"

  const urlHint = isUpdatingServiceSettings
    ? "Saving…"
    : savedUrl
      ? "Saved"
      : "Not set"
  function keyHint(key: ApiKeyFieldMeta): string {
    if (keyEdits[key.payload]) return "Unsaved"
    return current?.[key.setFlag] ? "Saved" : "Not set"
  }

  function clearSavedKey(key: ApiKeyFieldMeta) {
    // Extras are cleared by saving an explicit empty value (the regular
    // convention is "blank keeps current", so blanking alone cannot clear).
    saveService({ [key.payload]: "" })
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
        <div>
          <CardTitle>{label}</CardTitle>
          <CardDescription>Connection settings for {label}.</CardDescription>
        </div>
        <ConnectionBadge state={connectionState} detail={snapshot?.detail} />
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {hasUrl ? (
          <Field
            label="URL"
            hint={urlHint}
            helpText="Base URL for this service, including protocol and port when required."
          >
            <Input
              value={url}
              onChange={(event) => editUrl(event.target.value)}
              placeholder="http://host:port"
            />
            {urlLooksInternal ? (
              <p className="text-xs text-amber-600 dark:text-amber-400">
                This hostname may not be reachable from your browser. Use the
                external IP or hostname if you want dashboard and trending links
                to work.
              </p>
            ) : null}
          </Field>
        ) : null}
        {keyFields.map((key) => (
          <Field
            key={key.payload}
            label={key.label}
            hint={keyHint(key)}
            helpText={
              key.payload === "api_key"
                ? "API key saved server-side. Existing keys are never returned to the browser."
                : "Optional rotation key: lookups switch to it when the previous key hits its daily request limit."
            }
          >
            <Input
              type="password"
              value={keyEdits[key.payload] ?? ""}
              onChange={(event) => editKey(key.payload, event.target.value)}
              placeholder="Leave blank to keep current"
              aria-label={key.label}
            />
            {key.payload !== "api_key" && current?.[key.setFlag] ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="self-start text-muted-foreground"
                onClick={() => clearSavedKey(key)}
              >
                Remove this key
              </Button>
            ) : null}
          </Field>
        ))}
        <div className="flex flex-wrap gap-3">
          <ActionWithHelp
            label="Test connection"
            helpText="Checks the saved credentials or token without changing settings."
          >
            <Button
              variant="outline"
              onClick={() => test.mutate(name)}
              disabled={test.isPending}
            >
              Test connection
            </Button>
          </ActionWithHelp>
        </div>
        {test.data ? (
          <p
            className={cn(
              "text-sm",
              test.data.ok
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-destructive",
            )}
          >
            {test.data.detail}
          </p>
        ) : null}
        {name === "omdb" ? (
          <OmdbBudgetSection
            configuredKeys={
              keyFields.filter((key) => Boolean(current?.[key.setFlag])).length
            }
          />
        ) : null}
      </CardContent>
    </Card>
  )
}

/**
 * Editable per-key daily OMDb budget, shown beneath the Test connection block
 * on the OMDb tab. The value commits on blur, clamped to OMDb's free-tier
 * bounds; the summary line shows the effective daily total across the
 * configured keys.
 */
function OmdbBudgetSection({ configuredKeys }: { configuredKeys: number }) {
  const { data: general } = useGeneralSettings()
  const updateBudget = useUpdateOmdbBudget()
  const saved = general?.omdb_daily_budget_per_key ?? 800
  const [draft, setDraft] = useState<string | null>(null)

  function commit() {
    if (draft === null) return
    const trimmed = draft.trim()
    setDraft(null)
    // An emptied or unparseable input reverts to the saved value rather than
    // committing an accidental clamp-to-minimum.
    if (!trimmed) return
    // A number input only ever yields a valid float string or "" (handled
    // above), and the clamp folds even scientific-notation overflow back to
    // the bounds, so no separate finiteness guard is needed.
    const clamped = Math.max(100, Math.min(Math.round(Number(trimmed)), 1000))
    if (clamped !== saved) {
      updateBudget.mutate(clamped)
    }
  }

  return (
    <Field
      label="Daily request budget per key"
      hint={updateBudget.isPending ? "Saving…" : "Saved"}
      helpText="OMDb's free tier allows 1,000 requests per key per day; the default of 800 leaves headroom for poster lookups. The rating backfill spends at most this many requests per key per day."
    >
      <Input
        type="number"
        min={100}
        max={1000}
        step={50}
        value={draft ?? String(saved)}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        aria-label="Daily request budget per key"
      />
      <p className="text-xs text-muted-foreground">
        {configuredKeys > 0
          ? `${saved} × ${configuredKeys} key${configuredKeys === 1 ? "" : "s"} = ${saved * configuredKeys} rating lookups/day`
          : "No API key configured — the rating backfill is skipped."}
      </p>
    </Field>
  )
}

const STATUS_INTERVAL_OPTIONS = [30, 45, 60] as const

/** Storage overview and destructive clear actions for the local database. */
function DatabaseCard() {
  const { data: stats, isLoading } = useDatabaseStats()
  const clearActivity = useClearActivity()
  const clearItems = useClearItems()
  const clearPosters = useClearPosters()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Database</CardTitle>
        <CardDescription>
          Storage used by the local SQLite database and cached poster
          thumbnails.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {isLoading || !stats ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1">
                <span className="text-sm font-medium">Database size</span>
                <span className="text-2xl font-semibold">
                  {formatBytes(stats.db_size_bytes)}
                </span>
                <span className="text-xs text-muted-foreground">
                  Includes the main file, WAL, and SHM sidecars.
                </span>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-sm font-medium">Poster cache</span>
                <span className="text-2xl font-semibold">
                  {formatBytes(stats.poster_cache_bytes)}
                </span>
                <span className="text-xs text-muted-foreground">
                  Cached *.jpg thumbnails for list and Trending posters, fetched
                  on demand and evicted automatically once stale.
                </span>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="flex flex-col gap-0.5 rounded-md border p-3">
                <span className="text-xs text-muted-foreground">
                  Tracked items
                </span>
                <span className="text-lg font-semibold">
                  {stats.item_count}
                </span>
              </div>
              <div className="flex flex-col gap-0.5 rounded-md border p-3">
                <span className="text-xs text-muted-foreground">
                  Activity entries
                </span>
                <span className="text-lg font-semibold">
                  {stats.activity_count}
                </span>
              </div>
              <div className="flex flex-col gap-0.5 rounded-md border p-3">
                <span className="text-xs text-muted-foreground">
                  Synced lists
                </span>
                <span className="text-lg font-semibold">
                  {stats.list_state_count}
                </span>
              </div>
            </div>

            <div className="flex flex-col gap-3 rounded-md border border-destructive/50 p-4">
              <div>
                <p className="text-sm font-medium text-destructive">
                  Danger zone
                </p>
                <p className="text-xs text-muted-foreground">
                  These actions are destructive and cannot be undone.
                  Credentials, Trakt tokens, and tracked-list configuration are
                  never deleted.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <ClearAction
                  label="Clear activity log"
                  description="Empty the entire activity log. A single audit entry will remain."
                  confirmLabel="Clear"
                  helpText="Deletes activity history only; credentials and list configuration remain."
                  disabled={clearActivity.isPending}
                  onConfirm={() => clearActivity.mutate()}
                />
                <ClearAction
                  label="Clear synced items & sync state"
                  description="Delete every tracked item and list sync state. Your tracked-list configuration is preserved and the next sync rebuilds the data."
                  confirmLabel="Clear"
                  helpText="Deletes mirrored list items and sync state so the next sync rebuilds them."
                  disabled={clearItems.isPending}
                  onConfirm={() => clearItems.mutate()}
                />
                <ClearAction
                  label="Clear poster cache"
                  description="Delete every cached poster thumbnail (both list and Trending posters). They will be re-fetched on demand. Stale posters are also evicted automatically."
                  confirmLabel="Clear"
                  helpText="Deletes all cached poster thumbnails (list and Trending). They are fetched again on demand."
                  disabled={clearPosters.isPending}
                  onConfirm={() => clearPosters.mutate()}
                />
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              Note: SQLite does not shrink the database file immediately after
              rows are deleted, so the reported size may not drop right away.
              There is no compact action.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * One labelled setting row with a bounded Select: name + help tooltip and a
 * muted one-line description on the left, the control on the right. Shared by
 * the General and App scheduler cards so every cadence row stays identical.
 */
function SettingsSelectRow({
  id,
  label,
  help,
  description,
  options,
  value,
  disabled,
  placeholder = "Select interval",
  onChange,
}: {
  id: string
  label: string
  help: ReactNode
  description: string
  options: ReadonlyArray<{ value: number; label: string }>
  value: number
  disabled: boolean
  placeholder?: string
  onChange: (value: number) => void
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <div className="flex items-center gap-1.5">
          <label htmlFor={id} className="text-sm font-medium">
            {label}
          </label>
          <SettingsHelp label={label}>{help}</SettingsHelp>
        </div>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <Select
        value={String(value)}
        onValueChange={(next) => onChange(Number(next))}
        disabled={disabled}
      >
        <SelectTrigger id={id} className="w-full sm:w-40">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={String(option.value)}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

/** App-wide settings: status-check interval and appearance. */
function GeneralCard() {
  const { theme, setTheme } = useTheme()
  const { data: general } = useGeneralSettings()
  const updateInterval = useUpdateStatusInterval()

  const interval = general?.interval_seconds ?? 60

  return (
    <Card>
      <CardHeader>
        <CardTitle>General</CardTitle>
        <CardDescription>
          App-wide settings. The theme control mirrors the header.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <SettingsSelectRow
          id="status-interval"
          label="Status check interval"
          help="How often the dashboard refreshes connection status for configured integrations."
          description="How often the dashboard pings each integration."
          options={STATUS_INTERVAL_OPTIONS.map((seconds) => ({
            value: seconds,
            label: `${seconds} seconds`,
          }))}
          value={interval}
          disabled={updateInterval.isPending}
          onChange={(seconds) =>
            updateInterval.mutate({ interval_seconds: seconds })
          }
        />

        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-1.5">
            <p className="text-sm font-medium">Appearance</p>
            <SettingsHelp label="Appearance">
              Changes the dashboard colour mode only; it does not change backend
              behaviour.
            </SettingsHelp>
          </div>
          <div className="flex flex-wrap gap-2">
            {THEME_OPTIONS.map((option) => (
              <Button
                key={option.value}
                size="sm"
                variant={theme === option.value ? "default" : "outline"}
                onClick={() => setTheme(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// Whole-day cadences expressed in minutes (the API field stays minutes-based).
const TRENDING_INTERVAL_OPTIONS = [
  { value: 1440, label: "1 day" },
  { value: 2880, label: "2 days" },
  { value: 4320, label: "3 days" },
] as const

const ANIME_IDS_REFRESH_OPTIONS = [
  { value: 1, label: "1 day" },
  { value: 3, label: "3 days" },
  { value: 5, label: "5 days" },
] as const

const RATING_TTL_OPTIONS = [
  { value: 5, label: "5 days" },
  { value: 7, label: "7 days" },
  { value: 10, label: "10 days" },
] as const

/** App scheduler: background refresh cadences for the Trending page's data. */
function AppSchedulerCard() {
  const { data: general } = useGeneralSettings()
  const updateTrendingInterval = useUpdateTrendingInterval()
  const updateAnimeIdsRefresh = useUpdateAnimeIdsRefresh()
  const updateRatingTtl = useUpdateRatingTtl()

  const interval = general?.trending_sync_interval_minutes ?? 1440
  const animeIdsRefreshDays = general?.anime_ids_refresh_days ?? 3
  const ratingTtlDays = general?.rating_ttl_days ?? 7

  return (
    <Card>
      <CardHeader>
        <CardTitle>App scheduler</CardTitle>
        <CardDescription>
          Background refresh of the Trending page's feeds and the anime id
          mapping, so opening it does not call Trakt, TMDB and Seer on every
          click.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <SettingsSelectRow
          id="trending-interval"
          label="Trending sync interval"
          help="How often the background job refreshes the trending and popular feeds from Trakt, TMDB and Seer."
          description="How often trending and popular feeds are refreshed."
          options={TRENDING_INTERVAL_OPTIONS}
          value={interval}
          disabled={updateTrendingInterval.isPending}
          onChange={(minutes) => updateTrendingInterval.mutate(minutes)}
        />
        <SettingsSelectRow
          id="anime-ids-refresh"
          label="Anime mapping refresh"
          help="How often the cached AniList/MAL → TMDB/TVDB id mapping (Fribb's anime-lists) is refreshed. Checked at start-up and hourly; the download happens on the first check after the cadence elapses."
          description="How often the anime id mapping is refreshed."
          options={ANIME_IDS_REFRESH_OPTIONS}
          value={animeIdsRefreshDays}
          disabled={updateAnimeIdsRefresh.isPending}
          placeholder="Select cadence"
          onChange={(days) => updateAnimeIdsRefresh.mutate(days)}
        />
        <SettingsSelectRow
          id="rating-ttl"
          label="Rating refresh window"
          help="How often a title's stored IMDb rating is refreshed from OMDb. Ratings change slowly, so longer windows save request quota; stale titles refresh as the daily budget allows."
          description="How often stored IMDb ratings are refreshed."
          options={RATING_TTL_OPTIONS}
          value={ratingTtlDays}
          disabled={updateRatingTtl.isPending}
          placeholder="Select window"
          onChange={(days) => updateRatingTtl.mutate(days)}
        />
      </CardContent>
    </Card>
  )
}

/**
 * Settings page: a header (title and one-line description) above a tab per area —
 * General, Database, Trakt, then one per managed service (Seer, Sonarr, Radarr,
 * TMDB, OMDb, SABnzbd, qBittorrent), driven by {@link SERVICE_TABS}. The header
 * mirrors the other top-level pages so the layout stays consistent.
 */
export function Settings() {
  const [activeTab, setActiveTab] = useState(() => {
    if (typeof localStorage === "undefined") return "general"
    const stored = localStorage.getItem(SETTINGS_TAB_STORAGE_KEY)
    return stored && VALID_TAB_VALUES.includes(stored) ? stored : "general"
  })

  function handleTabChange(next: string) {
    setActiveTab(next)
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(SETTINGS_TAB_STORAGE_KEY, next)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Connect Trakt and your media services, tune app-wide preferences, and
          manage local data.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="h-auto max-w-full flex-wrap justify-start">
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="database">Database</TabsTrigger>
          <TabsTrigger value="trakt">Trakt</TabsTrigger>
          {SERVICE_TABS.map((tab) => (
            <TabsTrigger key={tab.name} value={tab.name}>
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="general">
          <div className="flex flex-col gap-6">
            <GeneralCard />
            <AppSchedulerCard />
          </div>
        </TabsContent>
        <TabsContent value="database">
          <DatabaseCard />
        </TabsContent>
        <TabsContent value="trakt">
          <CredentialsCard />
        </TabsContent>
        {SERVICE_TABS.map((tab) => (
          <TabsContent key={tab.name} value={tab.name}>
            <ServiceConnectionCard
              key={tab.name}
              name={tab.name}
              label={tab.label}
              fields={tab.fields}
            />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
