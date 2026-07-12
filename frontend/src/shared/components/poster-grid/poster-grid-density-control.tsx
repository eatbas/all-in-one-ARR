import { LayoutGridIcon } from "lucide-react"

import { Slider } from "@/shared/components/ui/slider"
import {
  VALID_POSTER_DENSITIES,
  type PosterDensity,
} from "@/shared/components/poster-grid/poster-grid-density"

/**
 * Accessible posters-per-row density slider used by both Trending and
 * ListSyncarr. Presents the same 5–11 range, grid icon, numeric read-out, and
 * keyboard behaviour everywhere the control appears.
 */
export function PosterDensityControl({
  value,
  onChange,
  label = "Posters per row",
}: {
  /** Currently selected density. */
  value: PosterDensity
  /** Called whenever the slider thumb moves to a new allowed value. */
  onChange: (value: PosterDensity) => void
  /** Accessible name for the slider; defaults to "Posters per row". */
  label?: string
}) {
  return (
    <div className="flex items-center gap-2" title={label}>
      <LayoutGridIcon
        aria-hidden="true"
        className="size-4 text-muted-foreground"
      />
      <Slider
        aria-label={label}
        className="w-28"
        min={VALID_POSTER_DENSITIES[0]}
        max={VALID_POSTER_DENSITIES[VALID_POSTER_DENSITIES.length - 1]}
        step={1}
        value={[value]}
        onValueChange={([next]) => onChange(next as PosterDensity)}
      />
      <span className="w-4 text-sm tabular-nums text-muted-foreground">
        {value}
      </span>
    </div>
  )
}
