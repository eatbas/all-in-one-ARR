import { useState, type ReactNode } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { DryRunSwitch } from "@/components/dry-run-switch"
import { useTheme } from "@/components/theme-provider"
import { cn } from "@/lib/utils"
import { SERVICE_TABS, VALID_TAB_VALUES, type ServiceTab } from "@/lib/services"
import { SETTINGS_TAB_STORAGE_KEY } from "@/lib/settings-tab"
import { THEME_OPTIONS } from "@/lib/theme-options"
import {
  useAddTraktList,
  useGeneralSettings,
  useRemoveTraktList,
  useServiceSettings,
  useStartTraktAuth,
  useTestService,
  useTestTrakt,
  useTraktAuthStatus,
  useTraktLists,
  useTraktSettings,
  useUpdateServiceSettings,
  useUpdateStatusInterval,
  useUpdateTraktSettings,
} from "@/lib/queries"
import type {
  UpdateServicePayload,
  UpdateTraktSettings,
} from "@/lib/api"

/** A labelled form row with an optional saved/state hint. */
function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium">{label}</label>
        {hint ? (
          <span className="text-xs text-muted-foreground">{hint}</span>
        ) : null}
      </div>
      {children}
    </div>
  )
}

/** Edit and save the Trakt application credentials. */
function CredentialsCard() {
  const { data: settings, isLoading } = useTraktSettings()
  const update = useUpdateTraktSettings()
  const [clientId, setClientId] = useState("")
  const [clientSecret, setClientSecret] = useState("")
  const [user, setUser] = useState("")

  function save() {
    const body: UpdateTraktSettings = {}
    if (clientId) body.client_id = clientId
    if (clientSecret) body.client_secret = clientSecret
    if (user) body.user = user
    update.mutate(body)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Trakt credentials</CardTitle>
        <CardDescription>
          From your application at trakt.tv/oauth/applications. The secret is
          stored server-side and never shown again.
        </CardDescription>
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
            <Field label="Trakt user">
              <Input
                value={user}
                onChange={(event) => setUser(event.target.value)}
                placeholder={settings?.user ?? "me"}
              />
            </Field>
            <div>
              <Button onClick={save} disabled={update.isPending}>
                Save credentials
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}

/** Run the device-auth flow and test the saved connection. */
function ConnectionCard() {
  const { data: settings } = useTraktSettings()
  const { data: auth } = useTraktAuthStatus()
  const startAuth = useStartTraktAuth()
  const test = useTestTrakt()

  const connected = settings?.connected ?? false
  const pending = auth && auth.state === "pending" ? auth : undefined
  const failedMessage =
    auth && auth.state === "failed" ? auth.message : undefined

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
        <div>
          <CardTitle>Connection</CardTitle>
          <CardDescription>
            Authorise this app to read and update your Trakt lists.
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
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => startAuth.mutate()} disabled={startAuth.isPending}>
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
              <span className="font-mono font-semibold">{pending.user_code}</span>
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
      </CardContent>
    </Card>
  )
}

/** Show synced lists, add by URL, and toggle discovered lists. */
function ListsCard() {
  const { data: settings } = useTraktSettings()
  const connected = settings?.connected ?? false
  const lists = useTraktLists(connected)
  const add = useAddTraktList()
  const remove = useRemoveTraktList()
  const [url, setUrl] = useState("")

  function addByUrl() {
    add.mutate({ url })
    setUrl("")
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Lists</CardTitle>
        <CardDescription>
          Choose which Trakt lists to keep in sync (TV, Movies, Anime …).
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">Syncing</p>
          {(settings?.lists.length ?? 0) === 0 ? (
            <p className="text-sm text-muted-foreground">
              No lists selected yet.
            </p>
          ) : (
            <ul className="divide-y">
              {settings?.lists.map((item) => (
                <li
                  key={`${item.owner_user}:${item.slug}`}
                  className="flex items-center justify-between py-2"
                >
                  <span className="text-sm">
                    <span className="font-medium">{item.name}</span>{" "}
                    <span className="text-muted-foreground">
                      ({item.owner_user}/{item.slug})
                    </span>
                  </span>
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() =>
                      remove.mutate({
                        owner_user: item.owner_user,
                        slug: item.slug,
                      })
                    }
                    disabled={remove.isPending}
                  >
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">Add by Trakt URL</p>
          <div className="flex gap-2">
            <Input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://trakt.tv/users/me/lists/anime"
            />
            <Button onClick={addByUrl} disabled={add.isPending || !url}>
              Add
            </Button>
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">Your Trakt lists</p>
          {!connected ? (
            <p className="text-sm text-muted-foreground">
              Connect Trakt to discover your lists.
            </p>
          ) : lists.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading lists…</p>
          ) : (lists.data?.length ?? 0) === 0 ? (
            <p className="text-sm text-muted-foreground">
              No lists found on your account.
            </p>
          ) : (
            <ul className="divide-y">
              {lists.data?.map((entry) => (
                <li
                  key={`${entry.owner_user}:${entry.slug}`}
                  className="flex items-center justify-between py-2"
                >
                  <span className="text-sm">
                    <span className="font-medium">
                      {entry.name ?? entry.slug}
                    </span>{" "}
                    <span className="text-muted-foreground">
                      ({entry.item_count ?? 0} items)
                    </span>
                  </span>
                  <Switch
                    checked={entry.selected}
                    disabled={add.isPending || remove.isPending}
                    onCheckedChange={(checked) =>
                      checked
                        ? add.mutate({
                            owner_user: entry.owner_user,
                            slug: entry.slug,
                          })
                        : remove.mutate({
                            owner_user: entry.owner_user,
                            slug: entry.slug,
                          })
                    }
                    aria-label={`Sync ${entry.slug}`}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

/** Edit a service connection (URL / API key / login) and test it. */
function ServiceConnectionCard({ name, label, fields }: ServiceTab) {
  const { data: services } = useServiceSettings()
  const update = useUpdateServiceSettings()
  const test = useTestService()
  const current = services?.[name]
  const [url, setUrl] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")

  const hasUrl = fields.includes("url")
  const hasApiKey = fields.includes("apiKey")
  const hasUsername = fields.includes("username")
  const hasPassword = fields.includes("password")

  function save() {
    const body: UpdateServicePayload = {}
    if (hasUrl && url) body.url = url
    if (hasApiKey && apiKey) body.api_key = apiKey
    if (hasUsername && username) body.username = username
    if (hasPassword && password) body.password = password
    update.mutate({ name, body })
  }

  // The status badge reflects the service's primary secret (key or password).
  const configured = hasApiKey ? current?.api_key_set : current?.password_set
  const badgeLabel = hasApiKey
    ? configured
      ? "Key set"
      : "No key"
    : configured
      ? "Password set"
      : "No password"

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
        {hasApiKey ? (
          <Field label="API key" hint={current?.api_key_set ? "Saved" : "Not set"}>
            <Input
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="Leave blank to keep current"
            />
          </Field>
        ) : null}
        {hasUsername ? (
          <Field
            label="Username"
            hint={current?.username ? `Saved: ${current.username}` : "Not set"}
          >
            <Input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder={current?.username || "Username"}
            />
          </Field>
        ) : null}
        {hasPassword ? (
          <Field
            label="Password"
            hint={current?.password_set ? "Saved" : "Not set"}
          >
            <Input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Leave blank to keep current"
            />
          </Field>
        ) : null}
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

/** App-wide settings: dry-run, status-check interval, and appearance. */
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
      <TabsContent value="trakt" className="flex flex-col gap-6">
        <CredentialsCard />
        <ConnectionCard />
        <ListsCard />
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
