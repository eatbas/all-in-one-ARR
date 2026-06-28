import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/components/ui/alert-dialog"
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs"
import {
  ConnectionBadge,
  type ConnectionState,
} from "@/shared/components/connection-badge"
import { SettingsHelp } from "@/shared/components/settings-help"
import { useTheme } from "@/shared/components/theme-context"
import { cn } from "@/shared/lib/utils"
import { SERVICE_TABS, VALID_TAB_VALUES, type ServiceTab } from "@/shared/lib/services"
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
  useUpdateServiceSettings,
  useUpdateStatusInterval,
  useUpdateTraktSettings,
} from "@/shared/lib/queries"
import type {
  UpdateServicePayload,
  UpdateTraktSettings,
} from "@/shared/lib/api"
import { useQueryClient } from "@tanstack/react-query"

/** A labelled form row with a saved/state hint. */
function Field({
  label,
  hint,
  helpText,
  children,
}: {
  label: string
  hint: string
  helpText?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <label className="text-sm font-medium">{label}</label>
          {helpText ? <SettingsHelp label={label}>{helpText}</SettingsHelp> : null}
        </div>
        <span className="text-xs text-muted-foreground">{hint}</span>
      </div>
      {children}
    </div>
  )
}

function ActionWithHelp({
  label,
  helpText,
  children,
}: {
  label: string
  helpText: ReactNode
  children: ReactNode
}) {
  return (
    <div className="flex items-center gap-1.5">
      {children}
      <SettingsHelp label={label}>{helpText}</SettingsHelp>
    </div>
  )
}

const AUTOSAVE_DELAY_MS = 800

/**
 * Debounced autosave helper. Schedules `mutate(body)` after `AUTOSAVE_DELAY_MS`
 * whenever `body` is non-null, but skips scheduling while a matching save is
 * already in-flight. It also suppresses re-submission of an identical body
 * after a failed save settles back to `isPending === false`, preventing the
 * same failed payload from being retried automatically every debounce cycle.
 */
function useAutosave<TBody>({
  body,
  draftRevision,
  mutate,
  isPending,
  onSuccess,
}: {
  body: TBody | null
  draftRevision: number
  mutate: (body: TBody, options?: { onSuccess?: () => void }) => void
  isPending: boolean
  onSuccess: () => void
}): void {
  const lastSubmittedRevisionRef = useRef<number | null>(null)

  useEffect(() => {
    if (!body) {
      lastSubmittedRevisionRef.current = null
      return
    }
    if (isPending) return

    // Revisions are non-secret edit counters, so failed-save suppression does
    // not retain Trakt secrets or service API keys in component refs.
    if (draftRevision === lastSubmittedRevisionRef.current) return

    const timer = window.setTimeout(() => {
      lastSubmittedRevisionRef.current = draftRevision
      mutate(body, { onSuccess })
    }, AUTOSAVE_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [body, draftRevision, isPending, mutate, onSuccess])
}

/** Edit the Trakt credentials, authorise the app, and test the connection. */
function CredentialsCard() {
  const { data: settings, isLoading } = useTraktSettings()
  const { data: auth } = useTraktAuthStatus()
  const {
    mutate: updateTraktSettings,
    isPending: isUpdatingTraktSettings,
  } = useUpdateTraktSettings()
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
                    href={pending.verification_url ?? "https://trakt.tv/activate"}
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
  const [apiKey, setApiKey] = useState("")
  const [serviceDraftRevision, setServiceDraftRevision] = useState(0)

  // Every managed service carries an API key; only some also carry a URL.
  const hasUrl = fields.includes("url")
  const savedUrl = current?.url ?? ""
  const url = urlEdit ?? savedUrl

  const serviceBody = useMemo<UpdateServicePayload | null>(() => {
    const body: UpdateServicePayload = {}
    if (hasUrl && url.trim() !== savedUrl.trim()) {
      body.url = url
    }
    if (apiKey) {
      body.api_key = apiKey
    }
    return Object.keys(body).length > 0 ? body : null
  }, [hasUrl, url, apiKey, savedUrl])

  const clearServiceEdit = useCallback(() => {
    setApiKey("")
    setUrlEdit(null)
  }, [])

  const editUrl = useCallback((value: string) => {
    setUrlEdit(value)
    setServiceDraftRevision((revision) => revision + 1)
  }, [])

  const editApiKey = useCallback((value: string) => {
    setApiKey(value)
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
  const apiKeyHint = apiKey
    ? "Unsaved"
    : current?.api_key_set
      ? "Saved"
      : "Not set"

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
          </Field>
        ) : null}
        <Field
          label="API key"
          hint={apiKeyHint}
          helpText="API key saved server-side. Existing keys are never returned to the browser."
        >
          <Input
            type="password"
            value={apiKey}
            onChange={(event) => editApiKey(event.target.value)}
            placeholder="Leave blank to keep current"
          />
        </Field>
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
      </CardContent>
    </Card>
  )
}

const STATUS_INTERVAL_OPTIONS = [30, 45, 60] as const

/** Danger-zone action with a confirmation dialog. */
function ClearAction({
  label,
  description,
  confirmLabel,
  helpText,
  disabled,
  onConfirm,
}: {
  label: string
  description: string
  confirmLabel: string
  helpText: ReactNode
  disabled: boolean
  onConfirm: () => void
}) {
  return (
    <ActionWithHelp label={label} helpText={helpText}>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="outline" disabled={disabled}>
            {label}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{label}?</AlertDialogTitle>
            <AlertDialogDescription>{description}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={onConfirm}>
              {confirmLabel}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ActionWithHelp>
  )
}

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
          Storage used by the local SQLite database and cached poster thumbnails.
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
                  Cached *.jpg thumbnails fetched on demand.
                </span>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="flex flex-col gap-0.5 rounded-md border p-3">
                <span className="text-xs text-muted-foreground">Tracked items</span>
                <span className="text-lg font-semibold">{stats.item_count}</span>
              </div>
              <div className="flex flex-col gap-0.5 rounded-md border p-3">
                <span className="text-xs text-muted-foreground">Activity entries</span>
                <span className="text-lg font-semibold">{stats.activity_count}</span>
              </div>
              <div className="flex flex-col gap-0.5 rounded-md border p-3">
                <span className="text-xs text-muted-foreground">Synced lists</span>
                <span className="text-lg font-semibold">{stats.list_state_count}</span>
              </div>
            </div>

            <div className="flex flex-col gap-3 rounded-md border border-destructive/50 p-4">
              <div>
                <p className="text-sm font-medium text-destructive">Danger zone</p>
                <p className="text-xs text-muted-foreground">
                  These actions are destructive and cannot be undone. Credentials,
                  Trakt tokens, and tracked-list configuration are never deleted.
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
                  description="Delete all cached poster thumbnails. They will be re-fetched on demand."
                  confirmLabel="Clear"
                  helpText="Deletes cached poster thumbnails. They are fetched again on demand."
                  disabled={clearPosters.isPending}
                  onConfirm={() => clearPosters.mutate()}
                />
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              Note: SQLite does not shrink the database file immediately after rows
              are deleted, so the reported size may not drop right away. There is no
              compact action.
            </p>
          </>
        )}
      </CardContent>
    </Card>
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
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-1.5">
              <label htmlFor="status-interval" className="text-sm font-medium">
                Status check interval
              </label>
              <SettingsHelp label="Status check interval">
                How often the dashboard refreshes connection status for
                configured integrations.
              </SettingsHelp>
            </div>
            <p className="text-sm text-muted-foreground">
              How often the dashboard pings each integration.
            </p>
          </div>
          <Select
            value={String(interval)}
            onValueChange={(value) =>
              updateInterval.mutate({ interval_seconds: Number(value) })
            }
            disabled={updateInterval.isPending}
          >
            <SelectTrigger id="status-interval" className="w-full sm:w-40">
              <SelectValue placeholder="Select interval" />
            </SelectTrigger>
            <SelectContent>
              {STATUS_INTERVAL_OPTIONS.map((seconds) => (
                <SelectItem key={seconds} value={String(seconds)}>
                  {seconds} seconds
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

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

/**
 * Settings page: a tab per area — General, Trakt, then one per managed service
 * (Seer, Sonarr, Radarr, TMDB, OMDb, SABnzbd, qBittorrent), driven by
 * {@link SERVICE_TABS}.
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
        <GeneralCard />
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
  )
}
