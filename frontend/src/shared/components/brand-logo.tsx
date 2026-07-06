import { useId } from "react"

import { cn } from "@/shared/lib/utils"

interface BrandLogoProps {
  className?: string
}

/**
 * The All-in-One ARR brand mark: the 2×2 "many apps unified" tile grid, drawn
 * entirely in `currentColor` so it inherits the surrounding text colour and
 * tracks the light/dark theme (`text-foreground` in the topbar,
 * `text-sidebar-foreground` in the sidebar). Depth comes from foreground opacity
 * steps rather than any hue, keeping the mark inside the monochrome theme.
 *
 * The mark is decorative — it is always paired with the visible "All-in-One ARR"
 * wordmark — so it is hidden from assistive technology.
 */
export function BrandLogo({ className }: BrandLogoProps) {
  // The mark can render more than once per page (topbar + sidebar), so the
  // knock-out mask needs a document-unique id to avoid duplicate ids clashing.
  // Sanitise `useId`'s output to keep the id a safe SVG fragment reference.
  const maskId = `aio-logo-dots-${useId().replace(/[^a-zA-Z0-9]/g, "")}`

  return (
    <svg
      viewBox="0 0 64 64"
      className={cn(className)}
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">
        <rect width="64" height="64" fill="#fff" />
        <rect x="43.35" y="43.35" width="4" height="4" rx="1.2" fill="#000" />
        <rect x="49.65" y="43.35" width="4" height="4" rx="1.2" fill="#000" />
        <rect x="43.35" y="49.65" width="4" height="4" rx="1.2" fill="#000" />
        <rect x="49.65" y="49.65" width="4" height="4" rx="1.2" fill="#000" />
      </mask>
      <rect x="7" y="7" width="22" height="22" rx="6" fill="currentColor" />
      <rect x="33" y="7" width="22" height="22" rx="6" fill="currentColor" opacity="0.68" />
      <rect x="7" y="33" width="22" height="22" rx="6" fill="currentColor" opacity="0.45" />
      <rect
        x="33"
        y="33"
        width="22"
        height="22"
        rx="6"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeDasharray="0.1 4.8"
        opacity="0.6"
      />
      <g transform="rotate(7 48.5 48.5)">
        <rect
          x="37.5"
          y="37.5"
          width="22"
          height="22"
          rx="6"
          fill="currentColor"
          opacity="0.92"
          mask={`url(#${maskId})`}
        />
      </g>
    </svg>
  )
}
