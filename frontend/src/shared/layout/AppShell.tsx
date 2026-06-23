import { NavLink, Outlet } from "react-router-dom"

import { cn } from "@/shared/lib/utils"
import { Topbar } from "@/shared/layout/Topbar"
import { NAV_ITEMS } from "@/shared/layout/nav-config"

/** Sidebar navigation rendered from the shared {@link NAV_ITEMS} config. */
function Sidebar() {
  return (
    <aside className="hidden w-56 shrink-0 border-r bg-sidebar md:block">
      <div className="flex h-16 items-center border-b px-6">
        <span className="text-sm font-semibold tracking-tight text-sidebar-foreground">
          aio-arr
        </span>
      </div>
      <nav className="flex flex-col gap-1 p-3">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            title={item.description}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground",
              )
            }
          >
            <item.icon className="size-4" />
            {item.title}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

/** Application layout: persistent sidebar + topbar wrapping routed pages. */
export function AppShell() {
  return (
    <div className="flex min-h-screen w-full">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
