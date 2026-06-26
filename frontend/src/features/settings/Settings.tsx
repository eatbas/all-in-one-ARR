import { useEffect, useRef, useState, type ReactNode } from "react"

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
import { Badge } from "@/shared/components/ui/badge"
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
  children,
}: {
  label: string
  hint: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium">{label}</label>
        <span className="text-xs text-muted-foreground">{hint}</span>
      </div>
      {children}
    </div>
  )
}

/** Edit the Trakt credentials, authorise the app, and test the connection. */
function CredentialsCard() {
  const { data: settings, isLoading } = useTraktSettings()
  const { data: auth } = useTraktAuthStatus()
  const update = useUpdateTraktSettings()
  const startAuth = useStartTraktAuth()
  const test = useTestTrakt()
  const queryClient = useQueryClient()
  const [clientId, setClientId] = useState("")
  const [clientSecret, setClientSecret] = useState("")

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

  function save() {
    const body: UpdateTraktSettings = {}
    if (clientId) body.client_id = clientId
    if (clientSecret) body.client_secret = clientSecret
    update.mutate(body)
  }

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
        <Badge
          variant="outline"
          className={cn(
            connected
              ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
              : "border-amber-500/40 text-amber-600 dark:text-amber-400",
          )}
        >
          {connected ? "Connected" : "Not connected"}
        </Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <>
            <Field
              label="Client ID"
              hint={
                settings?.client_id_set
                  ? `Saved (…${settings.client_id_hint})`
                  : "Not set"
              }
            >
              <Input
                value={clientId}
                onChange={(event) => setClientId(event.target.value)}
                placeholder="Trakt client id"
              />
            </Field>
            <Field
              label="Client secret"
              hint={settings?.client_secret_set ? "Saved" : "Not set"}
            >
              <Input
                type="password"
                value={clientSecret}
                onChange={(event) => setClientSecret(event.target.value)}
                placeholder="Leave blank to keep current"
              />
            </Field>
            <div className="flex flex-wrap gap-3">
              <Button onClick={save} disabled={update.isPending}>
                Save credentials
              </Button>
              <Button
                onClick={() => startAuth.mutate()}
                disabled={startAuth.isPending}
              >
                {connected ? "Re-connect Trakt" : "Connect Trakt"}
              </Button>
              <Button
                variant="outline"
                onClick={() => test.mutate()}
                disabled={test.isPending}
              >
                Test connection
              </Button>
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
  const update = useUpdateServiceSettings()
  const test = useTestService()
  const current = services?.[name]
  const [url, setUrl] = useState("")
  const [apiKey, setApiKey] = useState("")

  // Every managed service carries an API key; only some also carry a URL.
  const hasUrl = fields.includes("url")

  function save() {
    const body: UpdateServicePayload = {}
    if (hasUrl && url) body.url = url
    if (apiKey) body.api_key = apiKey
    update.mutate({ name, body })
  }

  // Every managed service authenticates with an API key, so the badge reflects
  // whether that key is set.
  const configured = current?.api_key_set
  const badgeLabel = configured ? "Key set" : "No key"

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
        <div>
          <CardTitle>{label}</CardTitle>
          <CardDescription>Connection settings for {label}.</CardDescription>
        </div>
        <Badge
          variant="outline"
          className={cn(
            configured
              ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
              : "border-amber-500/40 text-amber-600 dark:text-amber-400",
          )}
        >
          {badgeLabel}
        </Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {hasUrl ? (
          <Field
            label="URL"
            hint={current?.url ? `Saved: ${current.url}` : "Not set"}
          >
            <Input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder={current?.url || "http://host:port"}
            />
          </Field>
        ) : null}
        <Field label="API key" hint={current?.api_key_set ? "Saved" : "Not set"}>
          <Input
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="Leave blank to keep current"
          />
        </Field>
        <div className="flex flex-wrap gap-3">
          <Button onClick={save} disabled={update.isPending}>
            Save
          </Button>
          <Button
            variant="outline"
            onClick={() => test.mutate(name)}
            disabled={test.isPending}
          >
            Test connection
          </Button>
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
  disabled,
  onConfirm,
}: {
  label: string
  description: string
  confirmLabel: string
  disabled: boolean
  onConfirm: () => void
}) {
  return (
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
          <AlertDialogAction onClick={onConfirm}>{confirmLabel}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
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
                  disabled={clearActivity.isPending}
                  onConfirm={() => clearActivity.mutate()}
                />
                <ClearAction
                  label="Clear synced items & sync state"
                  description="Delete every tracked item and list sync state. Your tracked-list configuration is preserved and the next sync rebuilds the data."
                  confirmLabel="Clear"
                  disabled={clearItems.isPending}
                  onConfirm={() => clearItems.mutate()}
                />
                <ClearAction
                  label="Clear poster cache"
                  description="Delete all cached poster thumbnails. They will be re-fetched on demand."
                  confirmLabel="Clear"
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
        <div className="flex flex-col gap-2">
          <label htmlFor="status-interval" className="text-sm font-medium">
            Status check interval
          </label>
          <p className="text-sm text-muted-foreground">
            How often the dashboard pings each integration.
          </p>
          <Select
            value={String(interval)}
            onValueChange={(value) =>
              updateInterval.mutate({ interval_seconds: Number(value) })
            }
            disabled={updateInterval.isPending}
          >
            <SelectTrigger id="status-interval" className="w-40">
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

        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">Appearance</p>
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
      <TabsList>
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
            name={tab.name}
            label={tab.label}
            fields={tab.fields}
          />
        </TabsContent>
      ))}
    </Tabs>
  )
}
