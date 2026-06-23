import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { useTraktSettings } from "@/lib/queries"

/** Read-only view of the Trakt lists selected for syncing. */
export function Lists() {
  const { data: settings, isLoading } = useTraktSettings()
  const lists = settings?.lists ?? []

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Lists</h1>
        <p className="text-sm text-muted-foreground">
          Trakt lists kept in sync by the engine.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Synced lists</CardTitle>
          <CardDescription>
            Manage these from Settings → Trakt.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading lists…</p>
          ) : lists.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No lists selected yet.
            </p>
          ) : (
            <ul className="divide-y">
              {lists.map((item) => (
                <li
                  key={`${item.owner_user}:${item.slug}`}
                  className="flex items-center justify-between py-3 first:pt-0 last:pb-0"
                >
                  <span className="text-sm">
                    <span className="font-medium">{item.name}</span>{" "}
                    <span className="text-muted-foreground">
                      ({item.owner_user}/{item.slug})
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
