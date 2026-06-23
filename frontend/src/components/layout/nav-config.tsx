import {
  LayoutDashboardIcon,
  ListVideoIcon,
  ListIcon,
  SettingsIcon,
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
    title: "Lists",
    to: "/lists",
    icon: ListIcon,
    description: "Trakt List Sync status and integration health",
  },
  {
    title: "Items",
    to: "/items",
    icon: ListVideoIcon,
    description: "Browse every mirrored movie and show",
  },
  {
    title: "Settings",
    to: "/settings",
    icon: SettingsIcon,
    description: "Connect Trakt and choose which lists to sync",
  },
]
