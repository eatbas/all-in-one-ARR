import { useEffect, useRef, useState } from "react"
import { PanelLeftCloseIcon, PanelLeftOpenIcon } from "lucide-react"
import { NavLink, Outlet, useLocation } from "react-router-dom"

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
 * hover. The sidebar is a static, full-height child of the fixed-height app
 * shell — the document never scrolls (see `index.css`), so the rail and its
 * `mt-auto` version footer physically cannot leave the viewport however tall
 * the routed page grows; only `<main>` scrolls past it.
 */
function Sidebar({ collapsed, onToggle }: SidebarProps) {
  return (
    <aside
      id="primary-sidebar"
      className={cn(
        "hidden h-full shrink-0 flex-col border-r bg-sidebar transition-[width] duration-200 md:flex",
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

/**
 * Application layout: persistent sidebar + topbar wrapping routed pages.
 *
 * App-shell scroll model: the shell is a fixed viewport-height frame
 * (`h-dvh overflow-hidden`) and `<main>` is the only scroll container. The
 * document itself never scrolls, so overlay scroll locks that target `<body>`
 * (react-remove-scroll under every modal Radix primitive) are no-ops by
 * construction and can never re-anchor or hide the chrome.
 */
export function AppShell() {
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof localStorage === "undefined") return false
    return localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "true"
  })
  const mainRef = useRef<HTMLElement | null>(null)
  const { pathname } = useLocation()

  // Focus the scroll pane on load and on every navigation: the document no
  // longer scrolls, so with focus resting on <body> the scrolling keys
  // (PageDown, Space, arrows) would target the clipped document scroller and
  // do nothing until a click landed inside the pane. `preventScroll` keeps
  // the focus move itself from jumping the pane.
  useEffect(() => {
    mainRef.current?.focus({ preventScroll: true })
  }, [pathname])

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
    <div className="flex h-dvh w-full overflow-hidden">
      <Sidebar collapsed={collapsed} onToggle={toggleSidebar} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        {/* tabIndex={-1}: programmatically focusable (see the route-change
            effect above) without entering the Tab order; the pane is a
            landmark, not a control, so no focus outline. */}
        <main
          ref={mainRef}
          tabIndex={-1}
          className="flex-1 overflow-y-auto scrollbar-gutter-stable p-4 outline-none md:p-6"
        >
          <Outlet />
        </main>
      </div>
    </div>
  )
}
