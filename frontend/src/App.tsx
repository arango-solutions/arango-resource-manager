import { useQuery } from '@tanstack/react-query'
import { Route, Routes } from 'react-router-dom'

import SideMenu from './components/layout/SideMenu'
import TopBar from './components/layout/TopBar'
import { fetchClusterInfo } from './lib/api'
import { capabilityChips } from './lib/capability'
import Overview from './pages/Overview'
import Placeholder from './pages/Placeholder'

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
            <Route path="/" element={<Overview info={data} error={error as Error | null} />} />
            <Route
              path="/services"
              element={
                <Placeholder title="Services" phase="Phase 1">
                  Platform services, grouped from ArangoPlatformService and the
                  app.kubernetes.io/instance label, with health drawn from the real status
                  conditions.
                </Placeholder>
              }
            />
            <Route
              path="/pods"
              element={
                <Placeholder title="Pods" phase="Phase 1">
                  Every pod with its uptime, restart count, and live CPU and memory against what it
                  reserved.
                </Placeholder>
              }
            />
            <Route
              path="/capacity"
              element={
                <Placeholder title="Capacity" phase="Phase 2">
                  Used versus reserved versus limits, the overcommit ratio, the pods with no limits
                  set, and the waste leaderboard ranked by reclaimable cores.
                </Placeholder>
              }
            />
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
            <Route
              path="/settings"
              element={
                <Placeholder title="Settings" phase="Phase 2">
                  The namespace budget, the cost rates, and a readout of which capabilities this
                  credential actually has.
                </Placeholder>
              }
            />
          </Routes>
        </main>
      </div>
    </div>
  )
}
