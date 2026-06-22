import { Switch } from "@/components/ui/switch"
import { useSetDryRun, useStatus } from "@/lib/queries"

/**
 * The DRY_RUN toggle, shared by the header (Topbar) and the General settings
 * tab. Reads the live status and forwards changes to the dry-run mutation;
 * disabled while the toggle is in flight or before the status has loaded.
 */
export function DryRunSwitch({ id }: { id?: string }) {
  const { data: status } = useStatus()
  const setDryRun = useSetDryRun()

  return (
    <Switch
      id={id}
      checked={status?.dry_run ?? true}
      disabled={setDryRun.isPending || status === undefined}
      onCheckedChange={(checked) => setDryRun.mutate(checked)}
      aria-label="Toggle dry-run mode"
    />
  )
}
