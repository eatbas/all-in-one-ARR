import type { FindarrAppName } from "@/shared/lib/api"

/** Per-app branding for the Findarr "Live Finds Executed" cards. */
interface AppBrand {
  /** User-facing service name. */
  label: string
  /** Path to the official logo served from `public/brand`. */
  logoSrc: string
  /**
   * Classes for the dark circular disc the logo sits on. Both official logos use
   * a light mark plus their brand accent, so they stay legible on a fixed dark
   * disc regardless of the surrounding theme.
   */
  discClass: string
  /** Classes for the glowing brand-coloured ring around the disc. */
  ringClass: string
  /** Text-colour class for the headline stat numbers (the brand accent). */
  accentClass: string
}

export const APP_BRAND: Record<FindarrAppName, AppBrand> = {
  sonarr: {
    label: "Sonarr",
    logoSrc: "/brand/sonarr.svg",
    discClass: "bg-slate-900",
    ringClass: "border-[#00ccff]/70 shadow-[0_0_28px_rgba(0,204,255,0.45)]",
    accentClass: "text-sky-600 dark:text-[#00ccff]",
  },
  radarr: {
    label: "Radarr",
    logoSrc: "/brand/radarr.svg",
    discClass: "bg-slate-900",
    ringClass: "border-[#ffc230]/70 shadow-[0_0_28px_rgba(255,194,48,0.45)]",
    accentClass: "text-amber-600 dark:text-[#ffc230]",
  },
}
