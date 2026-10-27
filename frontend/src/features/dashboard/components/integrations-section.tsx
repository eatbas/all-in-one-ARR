import { RefreshCwIcon } from "lucide-react"

import { Button } from "@/shared/components/ui/button"
import { IntegrationStatusCard } from "@/features/dashboard/components/integration-status-card"
import {
  browserServiceUrl,
  type ServicesStatusResponse,
} from "@/shared/lib/api"
import { formatTimestamp } from "@/shared/lib/format"
import {
  useCheckServiceStatuses,
  useServiceSettings,
  useServiceStatuses,
} from "@/shared/lib/queries"
import { SERVICE_TABS } from "@/shared/lib/services"
import { cn } from "@/shared/lib/utils"

/**
 * Connection health for Trakt and every configured service, with the last
 * check time and a "Check now" action. Sits at the top of the Dashboard.
 */
export function IntegrationsSection() {
  const { data: serviceStatuses, isLoading: servicesLoading } =
    useServiceStatuses()
  const { data: serviceSettings } = useServiceSettings()
  const checkNow = useCheckServiceStatuses()

  const services =
    serviceStatuses?.services ?? ({} as ServicesStatusResponse["services"])
  const lastCheck = serviceStatuses?.last_check_at

  return (
    <section
      aria-labelledby="integrations-title"
      className="flex flex-col gap-3"
    >
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2
            id="integrations-title"
            className="text-2xl font-semibold tracking-tight"
          >
            Integrations
          </h2>
          <p className="text-sm text-muted-foreground">
            Review the current connection status for every configured service.
          </p>
        </div>
        <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center">
          <p className="text-xs text-muted-foreground sm:text-right">
            {lastCheck
              ? `Last checked ${formatTimestamp(lastCheck)}`
              : "Not checked yet"}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => checkNow.mutate()}
            disabled={checkNow.isPending || servicesLoading}
          >
            <RefreshCwIcon
              className={cn(
                "mr-2 size-4",
                checkNow.isPending && "animate-spin",
              )}
            />
            Check now
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <IntegrationStatusCard
          label="Trakt"
          status={services["trakt"]}
          url="https://trakt.tv"
        />
        {SERVICE_TABS.map((tab) => (
          <IntegrationStatusCard
            key={tab.name}
            label={tab.label}
            status={services[tab.name]}
            url={
              tab.fields.includes("url")
                ? browserServiceUrl(serviceSettings?.[tab.name]?.url)
                : tab.homepage
            }
          />
        ))}
      </div>
    </section>
  )
}
