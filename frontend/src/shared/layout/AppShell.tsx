import { useState } from "react"
import { PanelLeftCloseIcon, PanelLeftOpenIcon } from "lucide-react"
import { NavLink, Outlet } from "react-router-dom"

import { BrandLogo } from "@/shared/components/brand-logo"
import { Button } from "@/shared/components/ui/button"
import { cn } from "@/shared/lib/utils"
import { APP_VERSION } from "@/shared/lib/version"
import { Topbar } from "@/shared/layout/Topbar"
import { NAV_ITEMS } from "@/shared/layout/nav-config"
import { SIDEBAR_COLLAPSED_STORAGE_KEY } from "@/shared/layout/sidebar-state"

interface SidebarProps {
  /** Whether the sidebar is reduced to an icon-only rail. */
  collapsed: boolean
  /** Toggles between the icon rail and the full labelled sidebar. */
  onToggle: () => void
}

/**
 * Sidebar navigation rendered from the shared {@link NAV_ITEMS} config. When
 * {@link SidebarProps.collapsed} is set the labels collapse to an icon-only
 * rail; labels stay in the accessibility tree (via `sr-only`) so links keep
 * their accessible names, and the native `title` tooltip surfaces each label on
 * hover. The sidebar is pinned to the viewport (`sticky`, full height) so its
 * `mt-auto` version footer stays visible however tall the routed page grows —
 * `<html>` remains the document scroller (see `index.css`), so only the right
 * pane scrolls past it.
 */
function Sidebar({ collapsed, onToggle }: SidebarProps) {
  return (
    <aside
      id="primary-sidebar"
      className={cn(
        "sticky top-0 z-30 hidden h-screen shrink-0 flex-col self-start border-r bg-sidebar transition-[width] duration-200 md:flex",
        collapsed ? "w-16" : "w-56",
      )}
    >
      <div
        className={cn(
          "flex h-16 items-center border-b",
          collapsed ? "justify-center px-2" : "justify-between px-6",
        )}
      >
        <span
          className={cn(
            "flex items-center gap-2 text-sm font-semibold tracking-tight text-sidebar-foreground",
            collapsed && "sr-only",
          )}
        >
          <BrandLogo className="size-5 shrink-0 text-sidebar-foreground" />
          aio-arr
        </span>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-controls="primary-sidebar"
          aria-expanded={!collapsed}
        >
          {collapsed ? (
            <PanelLeftOpenIcon className="size-4" />
          ) : (
            <PanelLeftCloseIcon className="size-4" />
          )}
        </Button>
      </div>
      <nav className="flex flex-col gap-1 p-3">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            title={collapsed ? item.title : item.description}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md py-2 text-sm font-medium transition-colors",
                collapsed ? "justify-center px-2" : "px-3",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground",
              )
            }
          >
            <item.icon className="size-4 shrink-0" />
            <span className={cn(collapsed && "sr-only")}>{item.title}</span>
          </NavLink>
        ))}
      </nav>
      <div
        className={cn(
          "mt-auto flex items-center border-t py-3 text-xs text-muted-foreground",
          collapsed ? "justify-center px-2" : "gap-1.5 px-4",
        )}
      >
        <span className={cn(collapsed && "sr-only")}>aio-arr</span>
        <span
          className={cn(!collapsed && "font-medium text-sidebar-foreground/80")}
        >
          v{APP_VERSION}
        </span>
      </div>
    </aside>
  )
}

/** Application layout: persistent sidebar + topbar wrapping routed pages. */
export function AppShell() {
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof localStorage === "undefined") return false
    return localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "true"
  })

  function toggleSidebar() {
    setCollapsed((prev) => {
      const next = !prev
      if (typeof localStorage !== "undefined") {
        localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(next))
      }
      return next
    })
  }

  return (
    <div className="flex min-h-screen w-full">
      <Sidebar collapsed={collapsed} onToggle={toggleSidebar} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
