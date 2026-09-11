import { useQuery } from '@tanstack/react-query'
import { Route, Routes } from 'react-router-dom'

import SideMenu from './components/layout/SideMenu'
import TopBar from './components/layout/TopBar'
import { fetchClusterInfo } from './lib/api'
import { capabilityChips } from './lib/capability'
import Overview from './pages/Overview'
import Placeholder from './pages/Placeholder'
import Capacity from './pages/Capacity'
import Pods from './pages/Pods'
import ServiceDetail from './pages/ServiceDetail'
import SettingsPage from './pages/Settings'
import Services from './pages/Services'

export default function App() {
  const { data, error, isPending } = useQuery({
    queryKey: ['cluster', 'info'],
    queryFn: fetchClusterInfo,
    staleTime: Infinity,
  })

  const healthy = isPending ? null : !error && !!data

  return (
    <div className="flex h-full">
      <SideMenu healthy={healthy} />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          namespace={data?.namespace}
          context={data?.context}
          chips={data ? capabilityChips(data) : []}
        />

        <main className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/services" element={<Services />} />
            <Route path="/services/:name" element={<ServiceDetail />} />
            <Route path="/pods" element={<Pods />} />
            <Route path="/capacity" element={<Capacity />} />
            <Route
              path="/database"
              element={
                <Placeholder title="Database" phase="Phase 4">
                  The ArangoDeployment tiers. Coordinators and gateways scale freely, dbservers
                  require draining, and agents are never scalable.
                </Placeholder>
              }
            />
            <Route
              path="/activity"
              element={
                <Placeholder title="Activity" phase="Phase 4">
                  An append-only log of every scale, stop, restart and delete this tool performed.
                </Placeholder>
              }
            />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
