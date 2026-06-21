import { Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { Dashboard } from "@/pages/Dashboard"
import { Items } from "@/pages/Items"

/** Client-side route table, nested inside the persistent {@link AppShell}. */
export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/items" element={<Items />} />
        {/* Unknown client-side routes fall back to the dashboard. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
