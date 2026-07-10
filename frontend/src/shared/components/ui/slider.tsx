import * as React from "react"
import { Slider as SliderPrimitive } from "radix-ui"

import { cn } from "@/shared/lib/utils"

/**
 * Styled wrapper over Radix's Slider primitive, matching the project's
 * shadcn-style tokens (see {@link Switch}). One thumb is rendered per value in
 * the controlled `value` (or `defaultValue`) array. Intended for single-thumb
 * sliders: `aria-label`/`aria-labelledby` are forwarded to the sole thumb
 * because Radix places the `slider` role — and therefore the accessible name —
 * on the thumb rather than the root. A range (multi-thumb) slider must label
 * each thumb distinctly, so the shared name is deliberately not duplicated
 * across thumbs; give such a slider per-thumb labels instead.
 */
function Slider({
  className,
  value,
  defaultValue,
  "aria-label": ariaLabel,
  "aria-labelledby": ariaLabelledby,
  ...props
}: React.ComponentProps<typeof SliderPrimitive.Root>) {
  const thumbCount = Array.isArray(value)
    ? value.length
    : Array.isArray(defaultValue)
      ? defaultValue.length
      : 1

  return (
    <SliderPrimitive.Root
      data-slot="slider"
      value={value}
      defaultValue={defaultValue}
      className={cn(
        "relative flex w-full touch-none items-center select-none data-[disabled]:opacity-50",
        className,
      )}
      {...props}
    >
      <SliderPrimitive.Track
        data-slot="slider-track"
        className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-muted"
      >
        <SliderPrimitive.Range
          data-slot="slider-range"
          className="absolute h-full bg-primary"
        />
      </SliderPrimitive.Track>
      {Array.from({ length: thumbCount }, (_, index) => (
        <SliderPrimitive.Thumb
          key={index}
          data-slot="slider-thumb"
          // Only a single-thumb slider gets the shared name; duplicating one
          // label across every thumb of a range slider would be ambiguous.
          aria-label={thumbCount === 1 ? ariaLabel : undefined}
          aria-labelledby={thumbCount === 1 ? ariaLabelledby : undefined}
          className="block size-4 shrink-0 rounded-full border border-primary bg-background shadow-sm transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50"
        />
      ))}
    </SliderPrimitive.Root>
  )
}

export { Slider }
