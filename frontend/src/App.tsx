import { Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/shared/layout/AppShell"
import { Dashboard } from "@/features/dashboard/Dashboard"
import { ListSyncarr } from "@/features/list-syncarr/ListSyncarr"
import { Settings } from "@/features/settings/Settings"

/** Client-side route table, nested inside the persistent {@link AppShell}. */
export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/list-syncarr" element={<ListSyncarr />} />
        <Route path="/settings" element={<Settings />} />
        {/* Unknown client-side routes fall back to the dashboard. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
