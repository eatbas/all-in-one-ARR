import { useState, type ReactNode } from "react"

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
import { DryRunSwitch } from "@/shared/components/dry-run-switch"
import { useTheme } from "@/shared/components/theme-context"
import { cn } from "@/shared/lib/utils"
import { SERVICE_TABS, VALID_TAB_VALUES, type ServiceTab } from "@/shared/lib/services"
import { SETTINGS_TAB_STORAGE_KEY } from "@/features/settings/settings-tab"
import { THEME_OPTIONS } from "@/shared/lib/theme-options"
import {
  useGeneralSettings,
  useServiceSettings,
  useStartTraktAuth,
  useTestService,
  useTestTrakt,
  useTraktAuthStatus,
  useTraktSettings,
  useUpdateServiceSettings,
  useUpdateStatusInterval,
  useUpdateSyncInterval,
  useUpdateTraktSettings,
} from "@/shared/lib/queries"
import type {
  UpdateServicePayload,
  UpdateTraktSettings,
} from "@/shared/lib/api"

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
  const [clientId, setClientId] = useState("")
  const [clientSecret, setClientSecret] = useState("")

  const connected = settings?.connected ?? false
  const pending = auth && auth.state === "pending" ? auth : undefined
  const failedMessage =
    auth && auth.state === "failed" ? auth.message : undefined

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
const SYNC_INTERVAL_OPTIONS = [15, 30, 45, 60] as const

/** App-wide settings: dry-run, status-check interval, and appearance. */
function GeneralCard() {
  const { theme, setTheme } = useTheme()
  const { data: general } = useGeneralSettings()
  const updateInterval = useUpdateStatusInterval()
  const updateSyncInterval = useUpdateSyncInterval()

  const interval = general?.interval_seconds ?? 60
  const syncInterval = general?.sync_interval_minutes ?? 15

  return (
    <Card>
      <CardHeader>
        <CardTitle>General</CardTitle>
        <CardDescription>
          App-wide settings. These mirror the controls in the header.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium">Dry-run mode</p>
            <p className="text-sm text-muted-foreground">
              When on, requests and removals are only logged, never executed.
            </p>
          </div>
          <DryRunSwitch />
        </div>

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
          <label htmlFor="sync-interval" className="text-sm font-medium">
            Sync interval
          </label>
          <p className="text-sm text-muted-foreground">
            How often the engine polls Trakt and requests in Jellyseerr.
          </p>
          <Select
            value={String(syncInterval)}
            onValueChange={(value) => updateSyncInterval.mutate(Number(value))}
            disabled={updateSyncInterval.isPending}
          >
            <SelectTrigger id="sync-interval" className="w-40">
              <SelectValue placeholder="Select interval" />
            </SelectTrigger>
            <SelectContent>
              {SYNC_INTERVAL_OPTIONS.map((minutes) => (
                <SelectItem key={minutes} value={String(minutes)}>
                  {minutes} minutes
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
 * (Jellyseerr, Sonarr, Radarr, TMDB, OMDb, SABnzbd, qBittorrent), driven by
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
