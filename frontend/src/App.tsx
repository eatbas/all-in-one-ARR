import { Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/shared/layout/AppShell"
import { BandwidthControllarr } from "@/features/bandwidth-controllarr/BandwidthControllarr"
import { Dashboard } from "@/features/dashboard/Dashboard"
import { Deletarr } from "@/features/deletarr/Deletarr"
import { Findarr } from "@/features/findarr/Findarr"
import { ListSyncarr } from "@/features/list-syncarr/ListSyncarr"
import { Settings } from "@/features/settings/Settings"
import { Trending } from "@/features/trending/Trending"

/** Client-side route table, nested inside the persistent {@link AppShell}. */
export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/trending" element={<Trending />} />
        <Route path="/list-syncarr" element={<ListSyncarr />} />
        <Route
          path="/bandwidth-controllarr"
          element={<BandwidthControllarr />}
        />
        <Route path="/findarr" element={<Findarr />} />
        <Route path="/deletarr" element={<Deletarr />} />
        <Route path="/settings" element={<Settings />} />
        {/* Unknown client-side routes fall back to the dashboard. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
