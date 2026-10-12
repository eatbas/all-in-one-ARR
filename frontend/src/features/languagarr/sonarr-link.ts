import { isLikelyInternalUrl } from "@/shared/lib/api"
import { useLanguagarrStatus, useServiceSettings } from "@/shared/lib/queries"

/**
 * Browser-facing Sonarr base URL for the series links.
 *
 * Languagarr's `sonarr_link_url` wins; otherwise the Sonarr service URL is used
 * unless it looks Docker-internal (`http://sonarr:8989`), which a browser
 * cannot open. `undefined` hides the links.
 */
export function useSonarrLinkBase(): string | undefined {
  const override = useLanguagarrStatus().data?.settings.sonarr_link_url
  const serviceUrl = useServiceSettings().data?.sonarr.url
  if (override) return override
  if (serviceUrl && !isLikelyInternalUrl(serviceUrl)) return serviceUrl
  return undefined
}
