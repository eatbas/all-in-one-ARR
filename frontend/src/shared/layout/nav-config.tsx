import {
  GaugeIcon,
  LayoutDashboardIcon,
  ListChecksIcon,
  SearchIcon,
  SettingsIcon,
  Trash2Icon,
  TrendingUpIcon,
  type LucideIcon,
} from "lucide-react"

/** A single primary navigation entry. */
export interface NavItem {
  /** User-facing label. */
  title: string
  /** Client-side route path. */
  to: string
  /** Icon rendered beside the label. */
  icon: LucideIcon
  /** Short description used for tooltips and accessibility. */
  description: string
}

/**
 * Primary navigation, driven entirely by this array. Adding a new menu later is
 * a matter of adding an entry here (and a matching route in `App.tsx`).
 */
export const NAV_ITEMS: ReadonlyArray<NavItem> = [
  {
    title: "Dashboard",
    to: "/",
    icon: LayoutDashboardIcon,
    description: "Overview of sync counts and recent activity",
  },
  {
    title: "Trending",
    to: "/trending",
    icon: TrendingUpIcon,
    description: "Trending and popular movies and shows to add to a Trakt list",
  },
  {
    title: "List-Syncarr",
    to: "/list-syncarr",
    icon: ListChecksIcon,
    description: "Synced Trakt lists and their mirrored items",
  },
  {
    title: "Bandwidth-Controllarr",
    to: "/bandwidth-controllarr",
    icon: GaugeIcon,
    description: "Pause Usenet while torrents download",
  },
  {
    title: "Findarr",
    to: "/findarr",
    icon: SearchIcon,
    description: "Search missing and upgradeable Sonarr/Radarr media",
  },
  {
    title: "Deletarr",
    to: "/deletarr",
    icon: Trash2Icon,
    description: "Review and delete junk files from media libraries",
  },
  {
    title: "Settings",
    to: "/settings",
    icon: SettingsIcon,
    description: "Connect Trakt and choose which lists to sync",
  },
]
